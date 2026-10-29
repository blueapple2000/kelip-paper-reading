#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prepare version-pinned paper materials (Python 3.10+).

  python fetch_paper.py 2410.24164v1 --dest papers/example --level quick
  python fetch_paper.py papers/example --level full
  python fetch_paper.py local.pdf --dest papers/local --offline
  python fetch_paper.py papers/example --code https://github.com/owner/repo

Resume by passing an existing paper directory. Use a new directory for a new
paper/version. Discovered repositories remain candidates; --code records a
manual selection. Downloaded repository code is never executed.
"""
import argparse
import datetime
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import unicodedata
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from common import VERSION, atomic_write, contained_path, read_json, write_json, sha256_file, source_hashes

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True  # import extract_figures 时别在 skill 目录里留 __pycache__

UA = f"kelip-paper-reading/{VERSION} (academic paper reader)"
NEW_ID = r'\d{4}\.\d{4,5}(?:v\d+)?'
OLD_ID = r'[a-z][a-z\-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?'
ARXIV_RE = re.compile(rf'(?<![\d.])({NEW_ID}|{OLD_ID})(?!\d)')
GREEK = {"π": "pi", "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon", "λ": "lambda",
         "μ": "mu", "σ": "sigma", "τ": "tau", "φ": "phi", "ω": "omega", "θ": "theta", "ρ": "rho"}
STOP = {"a", "an", "the", "of", "for", "and", "to", "in", "on", "with", "via", "from", "by", "is", "are", "towards",
        "toward", "at", "as", "its", "using", "we", "our"}


def log(msg):
    print(msg, flush=True)


# ---------------- 网络 ----------------

def http_get(urls, timeout=60, tries=2, max_bytes=200 * 1024 * 1024):
    """依次试这几个地址，返回 (内容, 最终地址)。全失败就抛最后一个错。"""
    if isinstance(urls, str):
        urls = [urls]
    last = None
    for url in urls:
        if urllib.parse.urlsplit(url).scheme != "https":
            raise ValueError("仅支持 HTTPS 下载")
        for i in range(tries):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    if urllib.parse.urlsplit(r.geturl()).scheme != "https":
                        raise ValueError("拒绝降级到 HTTP")
                    data = r.read(max_bytes + 1)
                    if len(data) > max_bytes:
                        raise ValueError("下载内容超过大小限制")
                    return data, r.geturl()
            except ValueError:
                raise
            except urllib.error.HTTPError as e:
                last = e
                if e.code not in (429, 500, 502, 503, 504):
                    break
            except Exception as e:  # noqa: BLE001 —— 网络错误五花八门，统一重试
                last = e
                time.sleep(1.5 * (i + 1))
    raise last


# ---------------- 输入解析 ----------------

def parse_target(target):
    p = Path(os.path.expanduser(target))
    if p.is_dir():
        return {"kind": "dir", "path": p.resolve()}
    if p.is_file() and p.suffix.lower() == ".pdf":
        m = ARXIV_RE.search(p.name)
        return {"kind": "local-pdf", "path": p.resolve(), "arxiv": m.group(1) if m else None}
    m = ARXIV_RE.search(target)
    host = (urllib.parse.urlsplit(target).hostname or "").lower()
    supported = host in {"arxiv.org", "www.arxiv.org", "export.arxiv.org", "alphaxiv.org", "www.alphaxiv.org", "papers.cool"}
    supported = supported or (host == "huggingface.co" and urllib.parse.urlsplit(target).path.startswith("/papers/"))
    if m and (supported or re.fullmatch(r'\s*(arXiv:)?' + re.escape(m.group(1)) + r'\s*', target, re.I)):
        return {"kind": "arxiv", "arxiv": m.group(1)}
    if target.startswith(("http://", "https://")):
        return {"kind": "url-pdf", "url": target}
    sys.exit(f"认不出这个输入：{target}（要 arXiv ID / 链接 / PDF 路径 / 已有目录）")


def tidy_title(t):
    """arXiv 标题里会带 LaTeX：'$π_0$: A Vision-...' → 'π0: A Vision-...'"""
    def inline(m):
        x = m.group(1)
        for k, v in {"\\pi": "π", "\\alpha": "α", "\\beta": "β", "\\lambda": "λ", "\\mu": "μ", "\\tau": "τ"}.items():
            x = x.replace(k, v)
        return re.sub(r'[_^{}\\]', '', x)
    return " ".join(re.sub(r'\$([^$]*)\$', inline, t).split())


def slugify(title, fallback):
    if not title:
        return fallback.replace("/", "-")
    t = "".join(GREEK.get(c, c) for c in title)
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    head, _, rest = t.partition(":")
    words = lambda s: [w for w in re.split(r'[^A-Za-z0-9]+', s.lower()) if w and w not in STOP]
    if rest and len(head.split()) <= 3:  # "π0: A Vision-Language-Action ..." → 方法名在冒号前
        name = []
        for w in words(head):
            if w.isdigit() and name:
                name[-1] += w
            else:
                name.append(w)
        parts = ["-".join(name)] + words(rest)[:3]
    else:
        parts = words(t)[:5]
    slug = "-".join(p for p in parts if p)[:60].strip("-")
    return slug or fallback.replace("/", "-")


def pick_dest(args, slug):
    if args.dest:
        return Path(os.path.expanduser(args.dest)).resolve()
    if args.root:
        return (Path(os.path.expanduser(args.root)) / slug).resolve()
    if Path("related_work").is_dir():
        return (Path("related_work") / slug).resolve()
    if os.environ.get("PAPERS_DIR"):
        return (Path(os.path.expanduser(os.environ["PAPERS_DIR"])) / slug).resolve()
    return (Path("papers") / slug).resolve()


# ---------------- arXiv：元数据、PDF、源码 ----------------

def arxiv_meta(aid):
    try:
        xml, _ = http_get(f"https://export.arxiv.org/api/query?id_list={aid}", timeout=40)
    except Exception as e:  # noqa: BLE001
        log(f"  ⚠ arXiv API 没连上（{e}），元数据从 PDF 里凑")
        return {}
    ns = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}
    try:
        e = ET.fromstring(xml).find("a:entry", ns)
    except ET.ParseError:
        return {}
    if e is None:
        return {}
    txt = lambda tag: " ".join((e.findtext(tag, default="", namespaces=ns) or "").split())
    idurl = txt("a:id")
    if "arxiv.org/abs/" not in idurl:
        return {}
    ver = re.search(r'v(\d+)$', idurl)
    return {
        "arxiv_id": aid.split("v")[0] if re.match(NEW_ID, aid) else re.sub(r'v\d+$', '', aid),
        "version": f"v{ver.group(1)}" if ver else "",
        "title": tidy_title(txt("a:title")),
        "authors": [" ".join(a.findtext("a:name", default="", namespaces=ns).split()) for a in e.findall("a:author", ns)],
        "published": txt("a:published")[:10],
        "updated": txt("a:updated")[:10],
        "abstract": txt("a:summary"),
        "comment": txt("x:comment"),
        "journal_ref": txt("x:journal_ref"),
        "categories": [c.get("term") for c in e.findall("a:category", ns)],
        "abs_url": f"https://arxiv.org/abs/{aid}",
    }


def hf_paper(aid):
    """Hugging Face Papers 收录了作者认领的代码仓库和项目页；连不上就算了。"""
    try:
        raw, _ = http_get(f"https://huggingface.co/api/papers/{aid.split('v')[0]}", timeout=12, tries=1)
        d = json.loads(raw)
        return {"github": d.get("githubRepo") or "", "project": d.get("projectPage") or ""}
    except Exception:  # noqa: BLE001
        return {}


def safe_extract(raw, dest):
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:*") as tf:
        members = []
        total = 0
        for m in tf:
            target = contained_path(root, m.name)
            if not (m.isdir() or m.isfile()) or m.issym() or m.islnk():
                raise ValueError(f"不允许特殊归档条目：{m.name}")
            total += m.size
            if len(members) >= 10000 or m.size > 100 * 1024 * 1024 or total > 500 * 1024 * 1024:
                raise ValueError("源码归档超过文件数或解压大小限制")
            members.append((m, target))
        for m, target in members:
            if m.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif m.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                with tf.extractfile(m) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)


def fetch_source(aid, src_dir):
    """返回 'tar' / 'single-tex' / 'pdf-only' / 'failed'。"""
    try:
        data, _ = http_get([f"https://arxiv.org/e-print/{aid}", f"https://export.arxiv.org/e-print/{aid}"], timeout=60)
    except Exception as e:  # noqa: BLE001
        log(f"  ⚠ 源码没下下来（{e}）")
        return "failed"
    if data[:4] == b"%PDF":
        return "pdf-only"
    raw = data
    if data[:2] == b"\x1f\x8b":
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
                raw = stream.read(500 * 1024 * 1024 + 1)
            if len(raw) > 500 * 1024 * 1024:
                raise ValueError("源码解压超过大小限制")
        except OSError:
            pass
    try:
        safe_extract(raw, src_dir)
        if any(src_dir.rglob("*.tex")):
            return "tar"
    except tarfile.TarError:
        pass
    if raw[:4] == b"%PDF":
        return "pdf-only"
    text = raw.decode("utf-8", errors="replace")
    if "\\documentclass" in text or "\\begin{document}" in text:
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "main.tex").write_text(text, encoding="utf-8")
        return "single-tex"
    return "failed"


def arxiv_id_from_pdf(pdf):
    """arXiv 生成的 PDF 第一页左边有竖排的 'arXiv:2410.24164v4 [cs.LG] ...' 水印。"""
    try:
        import fitz
        with fitz.open(str(pdf)) as d:
            m = re.search(r'arXiv:\s*(' + NEW_ID + '|' + OLD_ID + ')', d[0].get_text())
            return m.group(1) if m else None
    except Exception:  # noqa: BLE001
        return None


def title_from_pdf(pdf):
    """非 arXiv 的 PDF：先看文档属性里的标题，不像标题就取第一页上半部分字号最大的那几行。"""
    try:
        import fitz
        with fitz.open(str(pdf)) as d:
            t = (d.metadata or {}).get("title") or ""
            if len(t) > 12 and not re.search(r'untitled|microsoft word|\.pdf$|\.dvi$|^p\d+$', t, re.I):
                return " ".join(t.split())
            page = d[0]
            spans = []
            for b in page.get_text("dict")["blocks"]:
                for l in b.get("lines", []):
                    for sp in l["spans"]:
                        if sp["text"].strip() and sp["bbox"][1] < 0.45 * page.rect.height:
                            spans.append((round(sp["size"], 1), sp["bbox"][1], sp["text"].strip()))
            if not spans:
                return ""
            big = max(x[0] for x in spans)
            words = [x[2] for x in sorted(spans, key=lambda x: x[1]) if x[0] >= big - 0.5]
            return " ".join(" ".join(words).split())[:200]
    except Exception:  # noqa: BLE001
        return ""


# ---------------- LaTeX：拍平、宏、大纲 ----------------

VERB_ENVS = r'verbatim|Verbatim|lstlisting|minted|alltt'


def strip_comments(text):
    text = re.sub(r'\\begin\{comment\}.*?\\end\{comment\}', '', text, flags=re.S)
    out, verb = [], False
    for line in text.split("\n"):
        if re.search(r'\\begin\{(' + VERB_ENVS + r')\}', line):
            verb = True
        if verb:
            out.append(line)
            if re.search(r'\\end\{(' + VERB_ENVS + r')\}', line):
                verb = False
            continue
        if re.match(r'\s*%', line):  # 整行注释直接丢，不留空行
            continue
        out.append(re.sub(r'(?<!\\)%.*$', '', line))
    return "\n".join(out)


def drop_iffalse(text):
    """去掉 \\iffalse ... \\fi 包起来的废稿（会数嵌套的 \\ifxxx）。"""
    out, i = [], 0
    for m in re.finditer(r'\\iffalse\b', text):
        if m.start() < i:
            continue
        depth, j = 1, m.end()
        for t in re.finditer(r'\\(if(?!thenelse)[a-zA-Z@]*|fi)\b', text[m.end():]):
            depth += 1 if t.group(1) != "fi" else -1
            if depth == 0:
                j = m.end() + t.end()
                break
        else:
            continue
        out.append(text[i:m.start()])
        i = j
    out.append(text[i:])
    return "".join(out)


INPUT_RE = re.compile(r'\\(?:input|include|subfile)\s*\{([^}]+)\}|\\(?:sub)?import\s*\{([^}]*)\}\s*\{([^}]+)\}'
                      r'|\\input\s+([^\s{}\\]+)')


def flatten(path, root, seen=None, depth=0):
    root = Path(root).resolve()
    path = Path(path).resolve()
    if not path.is_relative_to(root):
        raise ValueError("LaTeX 引用超出源码目录")
    seen = seen or set()
    if depth > 12 or path in seen:
        return ""
    seen.add(path)
    text = drop_iffalse(strip_comments(path.read_text(encoding="utf-8", errors="ignore")))

    def repl(m):
        if m.group(1):
            name, base = m.group(1).strip(), path.parent
        elif m.group(3):
            name, base = m.group(3).strip(), (path.parent / m.group(2).strip())
        else:
            name, base = m.group(4).strip(), path.parent
        for cand in (base / name, root / name, base / (name + ".tex"), root / (name + ".tex")):
            if not cand.resolve().is_relative_to(root):
                raise ValueError(f"LaTeX 引用超出源码目录：{name}")
            if cand.is_file() and cand.suffix in (".tex", ".bbl", ".tikz", ".pgf", ""):
                if cand.suffix in (".tikz", ".pgf"):
                    return f"% [图：{cand.relative_to(root)}]"
                return flatten(cand.resolve(), root, seen, depth + 1)
        return m.group(0)

    return INPUT_RE.sub(repl, text)


def find_main_tex(src):
    readme = src / "00README.json"
    if readme.exists():
        try:
            for s in json.loads(readme.read_text()).get("sources", []):
                if s.get("usage") == "toplevel":
                    candidate = contained_path(src, s["filename"])
                    if candidate.is_file():
                        return candidate
        except (ValueError, KeyError):
            pass
    cands = []
    for p in src.rglob("*.tex"):
        if not p.resolve().is_relative_to(src.resolve()):
            raise ValueError("源码入口超出目录")
        if ".stale" in p.parts:
            continue
        txt = p.read_text(encoding="utf-8", errors="ignore")
        if re.search(r'^\s*\\documentclass', txt, re.M):
            score = (10 if "\\begin{document}" in txt else 0) \
                + (3 if p.stem.lower() in ("main", "paper", "ms", "arxiv", "manuscript", "root") else 0) \
                + (2 if p.parent == src else 0) + min(len(txt) / 20000, 3)
            cands.append((score, str(p)))
    return Path(max(cands)[1]) if cands else None


DEF_RE = re.compile(r'\\(?:(?:re)?newcommand|providecommand|DeclareRobustCommand|DeclareMathOperator)\*?|\\def\s*(?=\\)')


def macro_defs(text):
    """正文前面定义的宏：返回 [(名字, 完整定义)]。"""
    from extract_figures import read_group
    out = []
    for m in DEF_RE.finditer(text):
        i = m.end()
        while i < len(text) and text[i] in " \t\n":
            i += 1
        if i >= len(text):
            break
        if text[i] == "{":
            j, name = read_group(text, i)
            name = name.strip()
        elif text[i] == "\\":
            nm = re.match(r'\\[A-Za-z@]+|\\.', text[i:])
            name, j = nm.group(0), i + nm.end()
        else:
            continue
        if not name.startswith("\\"):
            continue
        k = j
        if m.group(0).startswith("\\def"):
            pm = re.match(r'[^{]*', text[k:])
            k += pm.end()
        else:
            for _ in range(2):  # [参数个数][默认值]
                ws = re.match(r'\s*\[[^\]]*\]', text[k:])
                if ws:
                    k += ws.end()
        ws = re.match(r'\s*', text[k:])
        k += ws.end()
        if k < len(text) and text[k] == "{":
            end, _ = read_group(text, k)
            out.append((name, " ".join(text[m.start():end].split())))
    return out


def strip_bib(body):
    body = re.sub(r'\\begin\{thebibliography\}.*?\\end\{thebibliography\}', '', body, flags=re.S)
    body = re.sub(r'\\(?:bibliography|bibliographystyle|addbibresource)\s*\{[^}]*\}', '', body)
    return re.sub(r'\\printbibliography(\[[^\]]*\])?', '', body)


def build_tex(dest):
    src = dest / "source"
    main = find_main_tex(src) if src.is_dir() else None
    if not main:
        return None
    full = flatten(main.resolve(), src.resolve())
    b = full.find("\\begin{document}")
    e = full.rfind("\\end{document}")
    pre, body = (full[:b], full[b + len("\\begin{document}"):e if e > b else None]) if b >= 0 else ("", full)
    body = strip_bib(body)
    body = re.sub(r'\n[ \t]*\n(?:[ \t]*\n)+', '\n\n', body).strip("\n")
    used = []
    seen = set()
    for name, d in macro_defs(pre):
        if name in seen:
            continue
        if re.search(re.escape(name) + r'(?![A-Za-z@])', body):
            seen.add(name)
            used.append(d)
    head = [f"% paper.tex —— 由 source/{main.relative_to(src)} 拍平：\\input 已展开，注释、废稿（\\iffalse）、参考文献已去掉。",
            "% 读正文就读这个文件；行号和 outline.md 对得上。",
            f"% ==== 正文用到的自定义宏（{len(used)} 个；看不懂的记号先查这里）===="]
    head += used
    head += ["% ==== 正文 ===="]
    atomic_write(dest / "paper.tex", "\n".join(head) + "\n" + body + "\n")
    return {"main": str(main.relative_to(dest)), "macros": len(used),
            "lines": len(head) + body.count("\n") + 1}


EQ_ENVS = r'equation|align|gather|multline|eqnarray|flalign'


def build_outline(dest, meta):
    import extract_figures as ef  # noqa: F811
    L = [f"# 大纲 · {meta.get('title', '')}", ""]
    tex = dest / "paper.tex"
    if tex.exists():
        lines = tex.read_text(encoding="utf-8").split("\n")
        secs = ef.latex_sections(lines)
        levels = {}
        for i, line in enumerate(lines, 1):
            mm = re.search(r'\\(section|subsection|subsubsection)\*?\s*[\[{]', line)
            if mm:
                levels[i] = ["section", "subsection", "subsubsection"].index(mm.group(1))
        n = len(lines)
        L.append("行号指 `paper.tex`。读某一节：`sed -n '起,止p' paper.tex`（或用 Read 的 offset/limit）。")
        L.append("")
        abs_line = next((i for i, l in enumerate(lines, 1) if "\\begin{abstract}" in l), None)
        if abs_line:
            L.append(f"- L{abs_line} 摘要")
        app_line = next((i for i, l in enumerate(lines, 1) if re.match(r'\s*\\appendix\b', l)), None)
        for k, (i, num, title) in enumerate(secs):
            lvl = levels.get(i, 0)
            end = n
            for j, _, _ in secs[k + 1:]:
                if levels.get(j, 0) <= lvl:
                    end = j - 1
                    break
            if app_line and i > app_line and (k == 0 or secs[k - 1][0] < app_line):
                L.append(f"- L{app_line} —— 附录 ——")
            shown = title or ("（无标题，多半是附录开头）" if app_line and i > app_line else "（无标题）")
            L.append(f"{'  ' * lvl}- L{i}–{end} {(num + ' ') if num else ''}{shown}")
        # 公式：训练那一站找 loss 用
        eqs = []
        for m in re.finditer(r'\\begin\{(' + EQ_ENVS + r')(\*?)\}(.*?)\\end\{\1\2\}', "\n".join(lines), re.S):
            ln = "\n".join(lines).count("\n", 0, m.start()) + 1
            content = m.group(3)
            labels = re.findall(r'\\label\{([^}]+)\}', content)
            content = " ".join(re.sub(r'\\label\{[^}]+\}', '', content).split())
            eqs.append((ln, labels, content))
        for m in re.finditer(r'(?m)^\s*\\\[(.*?)\\\]', "\n".join(lines), re.S):
            ln = "\n".join(lines).count("\n", 0, m.start()) + 1
            eqs.append((ln, [], " ".join(m.group(1).split())))
        eqs.sort()
        if eqs:
            L += ["", f"## 公式（{len(eqs)} 个，按出现顺序；L 后面是所在小节）", ""]
            for ln, labels, content in eqs:
                lab = f" `{', '.join(labels)}`" if labels else ""
                prev = content[:110] + ("…" if len(content) > 110 else "")
                L.append(f"- L{ln} {ef.section_of(secs, ln)}{lab}：{prev}")
        L += ["", f"图表的页码、caption、在哪节被引用：见 `{ef.figures_dir(dest).name}/index.md`。"]
    else:
        L.append("没有 LaTeX 源码：正文读 `paper.txt`（按页分好了），公式只能看 PDF 渲染（`crop.py paper.pdf --page N`）。")
        L.append("")
        try:
            import fitz
            with fitz.open(str(dest / "paper.pdf")) as d:
                toc = d.get_toc()
            for lvl, title, page in toc:
                L.append(f"{'  ' * (lvl - 1)}- 第 {page} 页 · {title}")
            if not toc:
                L.append("（PDF 没有书签。用 `grep -n` 在 paper.txt 里找 Introduction / Method / Experiments 这类标题。）")
        except Exception:  # noqa: BLE001
            pass
        L += ["", f"图表的页码和 caption：见 `{ef.figures_dir(dest).name}/index.md`。"]
    atomic_write(dest / "outline.md", "\n".join(L) + "\n")


def build_txt(dest):
    try:
        import fitz
    except ImportError:
        if shutil.which("pdftotext"):
            subprocess.run(["pdftotext", "-layout", str(dest / "paper.pdf"), str(dest / "paper.txt")], check=False)
        return None
    from extract_figures import clean
    parts = []
    with fitz.open(str(dest / "paper.pdf")) as d:
        n = len(d)
        for i, page in enumerate(d, 1):
            text = "\n".join(l for l in clean(page.get_text()).split("\n")
                             if not l.strip() or l.count("\ufffd") < 0.3 * len(l.strip()))  # 图里字体抽出来的乱码行
            parts.append(f"\n===== 第 {i} 页 =====\n" + text)
    atomic_write(dest / "paper.txt", "".join(parts))
    return n


# ---------------- 代码 / 项目页链接 ----------------

URL_RE = re.compile(r'https?://[^\s<>"\'{}|\\^`\[\]]+')
SKIP_OWNERS = {"sponsors", "features", "orgs", "topics", "settings", "marketplace", "about", "login"}


def norm_url(u):
    u = u.rstrip(".,;:)]}>'\"")
    u = re.sub(r'#.*$', '', u)
    return u.rstrip("/")


def classify(u):
    parsed = urllib.parse.urlsplit(u)
    m = re.fullmatch(r'/([A-Za-z0-9_.\-]+)/([A-Za-z0-9_.\-]+)(?:/.*)?', parsed.path) if parsed.hostname == "github.com" else None
    if m:
        owner, repo = m.group(1), re.sub(r'\.git$', '', m.group(2))
        if owner.lower() in SKIP_OWNERS or repo.lower().endswith(".github.io"):
            return None, None  # 项目页模板（nerfies.github.io 之类）的致谢链接
        return "code", f"https://github.com/{owner}/{repo}"
    if re.search(r'huggingface\.co/(?!papers)', u):
        return "hf", u
    if ".github.io" in u or "sites.google.com" in u or re.search(r'project|page|website', u, re.I):
        return "project", u
    return "other", u


def collect_links(dest, meta, hf):
    score = defaultdict(lambda: {"score": 0, "from": []})

    def add(u, w, src, hint=""):
        if not u.startswith(("http://", "https://")):
            u = "https://" + u
        kind, url = classify(norm_url(u))
        if kind == "other" and re.search(r'project|website|videos|homepage', hint, re.I):
            kind = "project"
        if not kind or re.search(r'arxiv\.org|doi\.org|creativecommons', url or ""):
            return
        if kind == "other" and src in ("arXiv 备注", "摘要", "HF Papers"):
            kind = "project"
        s = score[(kind, url)]
        s["score"] += w
        if src not in s["from"]:
            s["from"].append(src)

    for u in URL_RE.findall(meta.get("comment", "")):
        add(u, 5, "arXiv 备注")
    for u in URL_RE.findall(meta.get("abstract", "")):
        add(u, 5, "摘要")
    if hf.get("github"):
        add(hf["github"], 6, "HF Papers")
    if hf.get("project"):
        add(hf["project"], 4, "HF Papers")
    try:
        import fitz
        with fitz.open(str(dest / "paper.pdf")) as d:
            for pno, page in enumerate(d):
                first = pno < 2
                for ln in page.get_links():
                    if ln.get("uri"):
                        add(ln["uri"], 4 if first else 0.5, "首页链接" if first else "正文链接")
                if first:
                    for u in URL_RE.findall(page.get_text()):
                        add(u, 3, "首页文字")
    except Exception:  # noqa: BLE001
        pass
    tex = dest / "paper.tex"
    if tex.exists():
        for line in tex.read_text(encoding="utf-8", errors="ignore").split("\n"):
            if re.search(r'code|github|release|available|project|website|open[- ]?source', line, re.I):
                for u in set(re.findall(r'\\(?:url|href)\{([^}]+)\}', line) + URL_RE.findall(line)):
                    add(u, 2, "正文提到", hint=line)
    out = defaultdict(list)
    merged = {}
    for (kind, url), s in score.items():  # 同一个地址先后被归成 other / project 时合并到 project
        key = url
        if key in merged and merged[key][0] == "project":
            merged[key][1]["score"] += s["score"]
            continue
        if key in merged and kind == "project":
            s["score"] += merged[key][1]["score"]
        merged[key] = (kind, s)
    for url, (kind, s) in sorted(merged.items(), key=lambda kv: -kv[1][1]["score"]):
        if kind == "other" and s["score"] < 2:  # 正文里顺手提到的商品 / 数据集网页，不是这篇的东西
            continue
        out[kind].append({"url": url, "score": round(s["score"], 1), "from": s["from"]})
    return dict(out)


def code_from_project_page(url):
    try:
        raw, _ = http_get(url, timeout=15, tries=1)
    except Exception:  # noqa: BLE001
        return None
    cnt = defaultdict(int)
    for u in URL_RE.findall(raw.decode("utf-8", errors="ignore")):
        kind, norm = classify(norm_url(u))
        if kind == "code":
            cnt[norm] += 1
    return max(cnt, key=cnt.get) if cnt else None


def normalize_repo(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.username or parsed.password:
        raise ValueError("代码仓库必须是 https://github.com/owner/repo 地址")
    if parsed.query or parsed.fragment or parsed.port not in (None, 443):
        raise ValueError("代码仓库地址不能带查询参数、片段或自定义端口")
    path = parsed.path.rstrip("/").removesuffix(".git")
    if not re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", path):
        raise ValueError("请提供仓库根地址")
    return "https://github.com" + path


def inspect_code(code_dir, expected_url):
    if not Path(code_dir).exists():
        return {"status": "not-cloned"}
    if not shutil.which("git"):
        return {"status": "no-git"}
    def git(*args):
        return subprocess.run(["git", "-C", str(code_dir), *args], capture_output=True,
                              text=True, timeout=15, check=True).stdout.strip()
    try:
        if Path(git("rev-parse", "--show-toplevel")).resolve() != Path(code_dir).resolve():
            return {"status": "invalid-existing-directory"}
        remote = normalize_repo(git("remote", "get-url", "origin"))
        if remote.lower() != normalize_repo(expected_url).lower():
            return {"status": "repository-mismatch"}
        return {"status": "exists", "url": remote, "commit": git("rev-parse", "HEAD"),
                "dirty": bool(git("status", "--porcelain"))}
    except (subprocess.SubprocessError, ValueError, OSError):
        return {"status": "invalid-existing-directory"}


def clone(url, code_dir):
    import tempfile
    url = normalize_repo(url)
    code_dir = Path(code_dir)
    if code_dir.exists() and (not code_dir.is_dir() or any(code_dir.iterdir())):
        return inspect_code(code_dir, url)["status"]
    if not shutil.which("git"):
        return "no-git"
    code_dir.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, GIT_LFS_SKIP_SMUDGE="1", GIT_TERMINAL_PROMPT="0")
    # Only clean our own temporary checkout, never the user's destination.
    with tempfile.TemporaryDirectory(prefix=".clone-", dir=code_dir.parent) as temp:
        checkout = Path(temp) / "code"
        try:
            r = subprocess.run(["git", "clone", "--depth", "1", "--single-branch", "--", url, str(checkout)],
                               env=env, capture_output=True, text=True, timeout=180)
            if r.returncode:
                return "failed: " + r.stderr.strip().split("\n")[-1][:160]
            if code_dir.exists():
                code_dir.rmdir()  # Fails safely if another process added files.
            checkout.rename(code_dir)
            return "ok"
        except subprocess.TimeoutExpired:
            return "timeout"


# ---------------- 主流程 ----------------

def main():
    import tempfile
    ap = argparse.ArgumentParser(description="准备可追溯的论文阅读材料；同一目录固定一个论文版本")
    ap.add_argument("target", help="arXiv ID / HTTPS PDF / 本地 PDF / 已有目录")
    destination = ap.add_mutually_exclusive_group()
    destination.add_argument("--dest")
    destination.add_argument("--root")
    ap.add_argument("--slug")
    ap.add_argument("--code-dir")
    ap.add_argument("--code", help="人工核对后的 GitHub 仓库根地址；不会自动认定搜索候选为官方")
    ap.add_argument("--no-clone", action="store_true")
    ap.add_argument("--offline", action="store_true", help="只用本地材料，禁止联网和克隆")
    ap.add_argument("--level", choices=("quick", "full"), default="full")
    ap.add_argument("--dpi", type=int, default=220)
    args = ap.parse_args()
    if not 72 <= args.dpi <= 600:
        ap.error("dpi 应在 72–600 之间")
    t = parse_target(args.target)
    if args.offline and t["kind"] in ("arxiv", "url-pdf"):
        ap.error("离线模式需要本地 PDF 或已有目录")
    requested = t.get("arxiv")
    dest = t["path"] if t["kind"] == "dir" else (Path(args.dest).expanduser().resolve() if args.dest else None)
    local_pdf = t.get("path") if t["kind"] == "local-pdf" else None
    downloaded_pdf = None
    if t["kind"] == "url-pdf":
        downloaded_pdf, _ = http_get(t["url"])
        if not downloaded_pdf.startswith(b"%PDF"):
            raise ValueError("链接返回的不是 PDF；请提供 PDF 直链或本地文件")
    if local_pdf:
        watermark = arxiv_id_from_pdf(local_pdf)
        if watermark and requested and re.sub(r"v\d+$", "", watermark) != re.sub(r"v\d+$", "", requested):
            raise ValueError("PDF 水印与文件名论文 ID 不一致")
        requested = watermark or requested
    previous = read_json(dest / "meta.json") if dest else {}
    existing_pdf = dest / "paper.pdf" if dest else None
    existing = bool(existing_pdf and existing_pdf.is_file())
    if existing and previous.get("pdf_sha256") and sha256_file(existing_pdf) != previous["pdf_sha256"]:
        raise ValueError("已有 PDF 与记录的哈希不符；请在新目录导入修改版")
    if existing and local_pdf and sha256_file(local_pdf) != sha256_file(existing_pdf):
        raise ValueError("目标目录已有不同 PDF；请使用新的 --dest")
    if existing and downloaded_pdf and hashlib.sha256(downloaded_pdf).hexdigest() != sha256_file(existing_pdf):
        raise ValueError("目标目录已有不同 PDF；请使用新的 --dest")
    observed = arxiv_id_from_pdf(existing_pdf) if existing else None
    pinned = previous.get("resolved_arxiv_id") or observed
    if existing and not pinned and previous.get("arxiv_id"):
        pinned = previous["arxiv_id"] + previous.get("version", "")
    if requested and pinned:
        base = lambda x: re.sub(r"v\d+$", "", x)
        if base(requested) != base(pinned) or (re.search(r"v\d+$", requested) and requested != pinned):
            raise ValueError("此目录已固定另一论文或版本；请使用新的 --dest")
    if existing and requested and not pinned:
        raise ValueError("无法确认已有 PDF 对应此论文；请使用新的 --dest")
    query_id = pinned or requested
    can_refresh = not existing or bool(pinned and re.search(r"v\d+$", pinned))
    fetched = arxiv_meta(query_id) if query_id and not args.offline and can_refresh else {}
    if query_id and re.search(r"v\d+$", query_id) and fetched.get("version"):
        if not query_id.endswith(fetched["version"]):
            raise ValueError("API 返回版本与固定版本不一致；停止以免混用")
    meta = dict(previous)
    for key, value in fetched.items():
        if value not in (None, "", []):
            meta[key] = value
    if not pinned and query_id:
        pinned = query_id if re.search(r"v\d+$", query_id) else (query_id + fetched["version"] if fetched.get("version") else None)
    if not meta.get("title") and local_pdf:
        meta["title"] = title_from_pdf(local_pdf)
    if dest is None:
        fallback = (pinned or requested or (local_pdf.stem if local_pdf else "paper" )).replace("/", "-")
        slug = args.slug or (slugify(meta.get("title", ""), fallback) + ("-" + fallback if requested else ""))
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", slug) or slug in (".", ".."):
            raise ValueError("slug 只能包含字母、数字、点、下划线和连字符")
        dest = pick_dest(args, slug)
        if (dest / "paper.pdf").exists():
            raise ValueError(f"目录已有论文，请直接传目录以补齐材料：{dest}")
    dest.mkdir(parents=True, exist_ok=True)
    pdf = dest / "paper.pdf"
    if not pdf.exists():
        if local_pdf:
            data = local_pdf.read_bytes()
        else:
            data = downloaded_pdf
            if data is None and query_id:
                data, _ = http_get([f"https://arxiv.org/pdf/{pinned or query_id}", f"https://export.arxiv.org/pdf/{pinned or query_id}"])
            if not data or not data.startswith(b"%PDF"):
                raise ValueError("没有有效 PDF")
        if previous.get("pdf_sha256") and hashlib.sha256(data).hexdigest() != previous["pdf_sha256"]:
            raise ValueError("待导入 PDF 与目录记录的哈希不同；请使用新的 --dest")
        import fitz
        with fitz.open(stream=data, filetype="pdf") as incoming_pdf:
            if incoming_pdf.needs_pass or len(incoming_pdf) == 0:
                raise ValueError("待导入 PDF 已加密或没有页面")
        atomic_write(pdf, data)
    import fitz
    with fitz.open(pdf) as check:
        if check.needs_pass or len(check) == 0:
            raise ValueError("PDF 已加密或没有页面")
    observed = arxiv_id_from_pdf(pdf)
    if observed and pinned and re.search(r"v\d+$", observed) and observed != pinned:
        raise ValueError("下载的 PDF 水印与请求版本不一致")
    pinned = observed or pinned
    verified_pdf_version = bool(observed and re.search(r"v\d+$", observed)) or (
        t["kind"] == "arxiv" and not existing and bool(pinned)) or bool(previous.get("pdf_version_verified"))
    meta.update({"schema_version": 2, "tool_version": VERSION, "pdf_sha256": sha256_file(pdf),
                 "resolved_arxiv_id": pinned, "pdf_version_verified": verified_pdf_version,
                 "fetched": datetime.date.today().isoformat()})
    if pinned:
        meta["arxiv_id"] = re.sub(r"v\d+$", "", pinned)
        version = re.search(r"v\d+$", pinned)
        if version:
            meta["version"] = version.group(0)
    if not meta.get("title"):
        meta["title"] = title_from_pdf(pdf)
    npages = build_txt(dest)
    meta["pdf_pages"] = npages
    text_chars = sum(len(line.strip()) for line in (dest / "paper.txt").read_text().splitlines() if not line.startswith("====="))
    meta["text_status"] = "needs-ocr-or-visual-reading" if text_chars < npages * 30 else "extracted"
    write_json(dest / "meta.json", meta)  # Save the fixed PDF identity before optional stages.
    log(f"▸ {meta.get('title', '')} · {pinned or '非 arXiv / 版本未确认'} → {dest}")
    src = dest / "source"
    before = source_hashes(src)
    if previous.get("source_sha256") and before != previous["source_sha256"]:
        raise ValueError("源码与既有记录不同；请保留原目录，在新目录导入修改版")
    if args.level == "full" and pinned and verified_pdf_version and not before and not args.offline:
        with tempfile.TemporaryDirectory(prefix=".source-", dir=dest) as tmp:
            incoming = Path(tmp) / "source"
            kind = fetch_source(pinned, incoming)
            if kind in ("tar", "single-tex"):
                if src.exists():
                    src.rmdir()
                incoming.rename(src)
                meta["source_arxiv_id"] = pinned
            meta["source_status"] = kind
    tex_info = None
    if src.is_dir() and any(src.rglob("*.tex")):
        if meta.get("source_arxiv_id") != pinned or not verified_pdf_version:
            meta["source_status"] = "user-or-legacy-source-unverified"
        tex_info = build_tex(dest)
    meta["source_sha256"] = source_hashes(src)
    meta["has_latex"] = bool(tex_info)
    meta["main_tex"] = tex_info["main"] if tex_info else None
    build_outline(dest, meta)
    links = previous.get("links", {})
    if args.level == "full":
        hf = hf_paper(pinned) if pinned and not args.offline else {}
        discovered = collect_links(dest, meta, hf)
        if discovered:
            links = discovered
    meta["links"] = links
    meta["code_candidates"] = links.get("code", [])
    # A score is a discovery hint, never proof of official ownership.
    selected = args.code or previous.get("selected_code")
    meta.pop("official_code", None)
    meta.pop("official_code_from", None)
    if selected:
        selected = normalize_repo(selected)
        code_dir = Path(args.code_dir).expanduser().resolve() if args.code_dir else Path(previous.get("code_dir") or dest / "code")
        state = inspect_code(code_dir, selected)["status"] if (args.offline or args.no_clone) else clone(selected, code_dir)
        info = inspect_code(code_dir, selected) if state in ("ok", "exists") else {"status": state}
        if state in ("repository-mismatch", "invalid-existing-directory"):
            raise ValueError(f"代码目录身份不匹配：{code_dir}；请指定新的 --code-dir")
        meta.update({"selected_code": selected, "code_selection": "user-specified", "code": info,
                     "code_dir": str(code_dir) if info.get("commit") else None})
    else:
        meta["code"] = {"status": "candidates-only", "verified_official": False}
        meta["code_dir"] = None
    write_json(dest / "meta.json", meta)
    if args.level == "full":
        import extract_figures
        items = extract_figures.extract(dest, dpi=args.dpi, quiet=True)
        log(f"  图表索引：{extract_figures.figures_dir(dest) / 'index.md'}（{len(items)} 项）")
    log(f"  文本：{meta['text_status']}；源码：{meta.get('source_status', 'not-fetched')}；代码：{meta['code']['status']}")
    log("下一步：核对版本和材料缺口，按 SKILL.md 的阅读模式讲解，并验证核心实验与局限。")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, RuntimeError) as exc:
        sys.exit(f"  ✗ {exc}")
