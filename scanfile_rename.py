import sys, subprocess, os, json, re, base64, tempfile, shutil, argparse, time, typing
from datetime import datetime

__version__="0.2.0"

def _env_first(names, default=None):
    for n in (names or []):
        v=os.getenv(n)
        if v is not None and str(v).strip() != "":
            return v
    return default

def _env_int_first(names, default_int: int) -> int:
    v=_env_first(names, None)
    if v is None:
        return int(default_int)
    try:
        return int(str(v).strip())
    except Exception:
        return int(default_int)

def _normalize_chat_completions_endpoint(endpoint: str) -> str:
    s=str(endpoint or "").strip()
    if not s:
        return s
    s=s.rstrip("/")
    if s.endswith("/v1/chat/completions"):
        return s
    if s.endswith("/v1"):
        return s+"/chat/completions"
    return s

LLM_ENDPOINT=_normalize_chat_completions_endpoint(
    _env_first(("LLM_ENDPOINT","LM_STUDIO_ENDPOINT"), "http://localhost:1234/v1/chat/completions")
)
LLM_MODEL=_env_first(("LLM_MODEL","LM_STUDIO_MODEL"), "qwen3-vl-8b-instruct")
LLM_TIMEOUT=_env_int_first(("LLM_TIMEOUT","LM_STUDIO_TIMEOUT"), 120)
LLM_MAX_RETRIES=_env_int_first(("LLM_MAX_RETRIES","LM_STUDIO_MAX_RETRIES"), 0)
PDFTOTEXT=os.getenv("PDFTOTEXT","/opt/homebrew/bin/pdftotext")
PDFTOPPM=os.getenv("PDFTOPPM","/opt/homebrew/bin/pdftoppm")
QPDF=os.getenv("QPDF","/opt/homebrew/bin/qpdf")
GS=os.getenv("GS","/opt/homebrew/bin/gs")

VISION_MAX_PAGES=int(os.getenv("VISION_MAX_PAGES","3"))
VISION_DPI=int(os.getenv("VISION_DPI","200"))
MIN_TEXT_CHARS=int(os.getenv("MIN_TEXT_CHARS","200"))

_PROGRESS_ENABLED=True
_PROGRESS_FORCE=os.getenv("FORCE_PROGRESS","0").strip().lower() in ("1","true","yes","y","on")

def _fmt_secs(s):
    try:
        s=float(s)
    except Exception:
        return "?s"
    if s < 1: return f"{int(s*1000)}ms"
    if s < 60: return f"{s:.1f}s"
    m=int(s//60); r=s-(m*60)
    if m < 60: return f"{m}m{int(r):02d}s"
    h=int(m//60); mm=m-(h*60)
    return f"{h}h{mm:02d}m"

def _progress(msg):
    if not _PROGRESS_ENABLED: return
    sys.stdout.write(str(msg).rstrip()+"\n")
    sys.stdout.flush()

def _run(cmd): return subprocess.run(cmd, capture_output=True, text=True)

def _tool_err(r):
    return (r.stderr or r.stdout or "").strip()

def _tool_exists(path_or_name):
    if not path_or_name: return None
    if os.path.isabs(path_or_name) and os.path.exists(path_or_name):
        return path_or_name
    return shutil.which(path_or_name)

def _looks_like_pdf_syntax_error(msg):
    s=str(msg or "").lower()
    return (
        "couldn't find trailer dictionary" in s or
        "couldn't read xref table" in s or
        "pdfsyntaxerror" in s or
        ("syntax error" in s and "xref" in s) or
        ("syntax error" in s and "trailer" in s)
    )

def _repair_pdf_to(pdf_input, pdf_output):
    qpdf=_tool_exists(QPDF) or _tool_exists("qpdf")
    if qpdf:
        _progress(f"  trying qpdf repair: {qpdf}")
        r=_run([qpdf, "--repair", pdf_input, pdf_output])
        if r.returncode == 0 and os.path.exists(pdf_output):
            return True, None
        err=_tool_err(r)
        _progress(f"  qpdf repair failed (rc={r.returncode}): {err[:200]}")

    gs=_tool_exists(GS) or _tool_exists("gs")
    if gs:
        _progress(f"  trying ghostscript rewrite: {gs}")
        r=_run([gs, "-o", pdf_output, "-sDEVICE=pdfwrite", "-dNOPAUSE", "-dBATCH", "-dSAFER", pdf_input])
        if r.returncode == 0 and os.path.exists(pdf_output):
            return True, None
        err=_tool_err(r)
        _progress(f"  ghostscript rewrite failed (rc={r.returncode}): {err[:200]}")

    return False, "No repair tool succeeded (qpdf/gs not available or failed)"

def _extract_json_loose(s):
    s=(s or "").strip()
    try: return json.loads(s)
    except: pass
    i=s.find("{"); j=s.rfind("}")
    if i!=-1 and j!=-1 and j>i:
        try: return json.loads(s[i:j+1])
        except: return None
    return None

def _img_to_data_url(path):
    b=base64.b64encode(open(path,"rb").read()).decode("utf-8")
    return f"data:image/jpeg;base64,{b}"

def _pdftotext(pdf_input):
    t0=time.monotonic()
    _progress(f"[1/4] Extracting text via pdftotext: {os.path.basename(pdf_input)}")
    r=_run([PDFTOTEXT, pdf_input, "-"])
    if r.returncode != 0:
        err=_tool_err(r)
        _progress(f"  pdftotext failed (rc={r.returncode}) in {_fmt_secs(time.monotonic()-t0)}")
        if err: _progress(f"  pdftotext error: {err[:200]}")
        return "", r.returncode, err
    out=(r.stdout or "").strip()
    _progress(f"  pdftotext ok: {len(out)} chars in {_fmt_secs(time.monotonic()-t0)}")
    return out, 0, ""

def _render_pdf_to_images(pdf_input, max_pages=VISION_MAX_PAGES, dpi=VISION_DPI):
    t0=time.monotonic()
    _progress(f"[2/4] Rendering PDF to images (pages={max_pages}, dpi={dpi})")
    with tempfile.TemporaryDirectory(prefix="scan_vlm_") as td:
        prefix=os.path.join(td, "page")
        r=_run([PDFTOPPM, "-f","1","-l",str(max_pages),"-r",str(dpi),"-jpeg", pdf_input, prefix])
        if r.returncode != 0:
            raise RuntimeError(_tool_err(r) or "pdftoppm failed")
        imgs=sorted([os.path.join(td,f) for f in os.listdir(td) if f.startswith("page-") and f.endswith(".jpg")],
                    key=lambda p: int(re.search(r"-(\d+)\.jpg$", p).group(1)))
        if not imgs: raise RuntimeError("No images produced from PDF")
        out=[_img_to_data_url(p) for p in imgs]
        _progress(f"  rendered {len(out)} image(s) in {_fmt_secs(time.monotonic()-t0)}")
        return out

def _is_context_overflow(err):
    s=str(err or "").lower()
    return ("context length" in s) or ("overflows" in s) or ("not enough" in s) or ("overflow" in s)

def _clean_err(resp):
    try:
        j=resp.json()
        return j.get("error") or j
    except Exception:
        return (resp.text or "").strip()

def _call_llm(messages, max_tokens=350, timeout=LLM_TIMEOUT, retries=LLM_MAX_RETRIES):
    import requests
    payload={"model":LLM_MODEL,"messages":messages,"temperature":0.0,"max_tokens":max_tokens}
    last_err=None
    for attempt in range(retries+1):
        try:
            resp=requests.post(LLM_ENDPOINT, headers={"Content-Type":"application/json"}, json=payload, timeout=timeout)
        except requests.RequestException as e:
            last_err=f"RequestException: {e}"
            if attempt < retries: continue
            return None, last_err
        if resp.status_code >= 500:
            last_err=str(_clean_err(resp))
            if attempt < retries: continue
            return None, last_err
        if resp.status_code >= 400:
            return None, _clean_err(resp)
        try:
            j=resp.json()
            return j["choices"][0]["message"]["content"], None
        except Exception as e:
            last_err=f"BadResponse: {e} | body={(resp.text or '')[:2000]}"
            if attempt < retries: continue
            return None, last_err
    return None, last_err or "UnknownError"

def _prompt_from_text(t, keywords_count=5):
    return f"""You rename scanned documents by extracting filename metadata.

Text from a scanned document:
{t}

Return ONLY valid JSON (no markdown, no extra text) with:
- date: best single date for the filename in YYYY-MM-DD (prefer date of service if this doc is about a service/appointment/delivery; otherwise prefer the document/issue date). null if unknown.
- date_basis: "service" | "document" | "unknown"
- provider: short issuer/vendor/provider/organization name (e.g., bank, utility, clinic, school). null if unknown.
- document_type: short type like "Statement", "Invoice", "Receipt", "Bill", "Report", "Letter", "Notice", "Contract", "Policy", "Form", "Tax Document", or similar. null if unknown.
- title: short human-readable title (max ~8 words). If the document already has a clear title, use it; otherwise infer one from content. null if unknown.
- author: short author (person or organization) if clear from the document. null if unknown.
- subject: short subject line if clear from the document. null if unknown.
- keywords: array of strings (max {keywords_count} items). Each keyword should be a short topic phrase. [] if none.
- confidence: number 0 to 1
"""

def _prompt_for_vision(partial=None, keywords_count=5):
    partial=json.dumps(partial or {}, ensure_ascii=False)
    return f"""You rename scanned documents by extracting filename metadata.

If the user provides partial extracted JSON, use it as hints, but correct any obvious mistakes.

Partial extracted JSON hints (may be incomplete/wrong):
{partial}

Return ONLY valid JSON (no markdown, no extra text) with:
- date: best single date for the filename in YYYY-MM-DD (prefer date of service if this doc is about a service/appointment/delivery; otherwise prefer the document/issue date). null if unknown.
- date_basis: "service" | "document" | "unknown"
- provider: short issuer/vendor/provider/organization name. null if unknown.
- document_type: short type like "Statement", "Invoice", "Receipt", "Bill", "Report", "Letter", "Notice", "Contract", "Policy", "Form", "Tax Document", or similar. null if unknown.
- title: short human-readable title (max ~8 words). If the document already has a clear title, use it; otherwise infer one from content. null if unknown.
- author: short author (person or organization) if clear from the document. null if unknown.
- subject: short subject line if clear from the document. null if unknown.
- keywords: array of strings (max {keywords_count} items). Each keyword should be a short topic phrase. [] if none.
- confidence: number 0 to 1
"""

def _compact_text(text, max_chars):
    t=(text or "").strip()
    if len(t) <= max_chars: return t
    lines=[ln.strip() for ln in t.splitlines() if ln.strip()]
    if not lines: return t[:max_chars]
    pats=[
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b",
        r"\b(invoice|statement|receipt|bill|balance|amount|total|due|paid|payment|account|acct|order|purchase)\b",
        r"\b(service|date of service|dos|appointment|visit|delivered|shipped)\b",
        r"\b(policy|contract|agreement|notice|letter|form|report|summary|renewal)\b",
        r"\b(tax|irs|1099|w-2|utility|electric|gas|water|internet|insurance|mortgage|bank|credit)\b",
    ]
    rx=re.compile("|".join(pats), re.I)
    picked=[ln for ln in lines if rx.search(ln)]
    s="\n".join(picked)
    if len(s) >= max_chars: return s[:max_chars]
    head="\n".join(lines[:250])
    tail="\n".join(lines[-250:])
    combo=(s+"\n\n"+head+"\n\n"+tail).strip()
    return combo[:max_chars]

def _normalize_date(s):
    if not s: return None
    s=str(s).strip()
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return s
    except: return None

def _normalize_doc_type(s):
    if not s: return None
    s=re.sub(r"\s{2,}"," ",str(s)).strip()
    s=re.sub(r"[^A-Za-z0-9 &/+-]","",s).strip()
    if not s: return None
    low=s.lower()
    m={
        "invoice":"Invoice","inv":"Invoice",
        "statement":"Statement",
        "receipt":"Receipt",
        "bill":"Bill",
        "report":"Report",
        "letter":"Letter",
        "notice":"Notice",
        "contract":"Contract","agreement":"Agreement",
        "policy":"Policy",
        "form":"Form",
        "summary":"Summary",
        "tax":"Tax Document",
    }
    for k,v in m.items():
        if re.search(rf"\b{re.escape(k)}\b", low): return v
    return " ".join(w.capitalize() for w in s.split())[:40]

def _unknown_count(info):
    info=info or {}
    c=0
    if not _normalize_date(info.get("date")): c+=1
    if not (info.get("provider") and str(info.get("provider")).strip()): c+=1
    if not _normalize_doc_type(info.get("document_type")): c+=1
    t=str(info.get("title") or "").strip()
    if len(t) < 3: c+=1
    return c

def _merge_fill_missing(base, extra):
    base=dict(base or {})
    extra=extra or {}
    # date
    if not _normalize_date(base.get("date")) and _normalize_date(extra.get("date")):
        base["date"]=extra.get("date")
    # simple string fields
    for k in ["date_basis","provider","document_type","title"]:
        if not (base.get(k) and str(base.get(k)).strip()) and (extra.get(k) and str(extra.get(k)).strip()):
            base[k]=extra.get(k)
    # confidence
    try:
        bc=float(base.get("confidence") or 0)
    except: bc=0
    try:
        ec=float(extra.get("confidence") or 0)
    except: ec=0
    base["confidence"]=max(bc, ec)
    return base

def _safe_filename(s, max_len=80):
    s=re.sub(r'[\r\n\t]+',' ',str(s or ""))
    s=re.sub(r'[\/\\:\*\?"<>\|]+','-',s)
    s=re.sub(r"\s{2,}"," ",s).strip()
    s=s.strip(" .-_")
    return (s[:max_len] or "")

def _unique_path(path):
    if not os.path.exists(path): return path
    root, ext=os.path.splitext(path)
    for i in range(2, 200):
        p=f"{root} ({i}){ext}"
        if not os.path.exists(p): return p
    return f"{root} ({os.getpid()}){ext}"

def _heuristic_extract(text):
    lines=[ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    top=lines[:60]
    date=None
    for ln in top:
        m=re.search(r"\b(\d{4}-\d{2}-\d{2})\b", ln)
        if m: date=m.group(1); break
    if not date:
        for ln in top:
            m=re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", ln)
            if not m: continue
            mm,dd,yy=m.group(1),m.group(2),m.group(3)
            yy=("20"+yy) if len(yy)==2 else yy
            try:
                d=datetime(int(yy),int(mm),int(dd))
                date=d.strftime("%Y-%m-%d")
                break
            except: pass
    provider=None
    for ln in top[:15]:
        if len(ln) >= 4 and not re.search(r"page\s+\d+", ln, re.I):
            if re.search(r"[A-Za-z]", ln):
                provider=ln
                break
    blob="\n".join(top).lower()
    dt=None
    for k,v in [("invoice","Invoice"),("statement","Statement"),("receipt","Receipt"),("bill","Bill"),("report","Report"),
                ("contract","Contract"),("agreement","Agreement"),("policy","Policy"),("notice","Notice"),("letter","Letter"),("form","Form")]:
        if k in blob: dt=v; break
    title=None
    for ln in top[:20]:
        if re.search(r"\b(invoice|statement|receipt|bill|report|contract|agreement|policy|notice|letter|form)\b", ln, re.I):
            title=ln
            break
    return {"date":date,"date_basis":"unknown","provider":provider,"document_type":dt,"title":title,"confidence":0.25}

def extract_information(pdf_input: str, lm_timeout: int=LLM_TIMEOUT, lm_retries: int=LLM_MAX_RETRIES, allow_repair: bool=True, keywords_count: int=5) -> typing.Tuple[typing.Optional[typing.Dict[str, typing.Any]], str]:
    repair_ctx=None
    work_pdf=pdf_input

    def _postprocess_llm_info(info):
        if not isinstance(info, dict):
            return info

        if "subject" in info:
            s=info.get("subject")
            if isinstance(s, str):
                lines=[ln.strip() for ln in s.splitlines() if ln.strip()]
                if lines:
                    info["subject"]=lines[0]
                else:
                    del info["subject"]
            else:
                del info["subject"]

        if "keywords" in info:
            kw=info.get("keywords")
            if isinstance(kw, list):
                k=[x.strip() for x in kw if isinstance(x, str) and x.strip()]
                try:
                    n=max(0, int(keywords_count))
                except Exception:
                    n=0
                if n:
                    info["keywords"]=k[:n]
                else:
                    info["keywords"]=[]
            else:
                del info["keywords"]

        if "author" in info:
            a=info.get("author")
            if isinstance(a, str):
                a=a.strip()
                if a:
                    info["author"]=a
                else:
                    del info["author"]
            else:
                del info["author"]

        return info

    def _try_repair(reason):
        nonlocal repair_ctx, work_pdf
        if not allow_repair:
            return False
        if repair_ctx is not None:
            return False
        if not _looks_like_pdf_syntax_error(reason):
            return False
        _progress("[0/4] Attempting to repair PDF for Poppler")
        repair_ctx=tempfile.TemporaryDirectory(prefix="scan_pdf_repair_")
        repaired=os.path.join(repair_ctx.name, "repaired.pdf")
        ok, err=_repair_pdf_to(pdf_input, repaired)
        if ok:
            work_pdf=repaired
            _progress("  using repaired PDF for extraction")
            return True
        _progress(f"  repair not available/failed: {err}")
        repair_ctx.cleanup()
        repair_ctx=None
        return False

    try:
        text, rc, err=_pdftotext(work_pdf)
        if rc != 0 and work_pdf == pdf_input:
            if _try_repair(err):
                text, rc, err=_pdftotext(work_pdf)

        def _vision_extract(partial_hint=None):
            page_tries=[VISION_MAX_PAGES, max(1, VISION_MAX_PAGES-1), 1]
            for idx, pages in enumerate(page_tries, start=1):
                _progress(f"[3/4] Vision pass {idx}/{len(page_tries)}: pages={pages}")
                try:
                    imgs=_render_pdf_to_images(work_pdf, max_pages=pages, dpi=VISION_DPI)
                except RuntimeError as e:
                    if work_pdf == pdf_input and _try_repair(e):
                        return _vision_extract(partial_hint=partial_hint)
                    raise
                prompt=_prompt_for_vision(partial_hint, keywords_count=keywords_count)
                content=[{"type":"text","text":prompt}] + [{"type":"image_url","image_url":{"url":u}} for u in imgs]
                t0=time.monotonic()
                _progress(f"  calling LLM (vision) model={LLM_MODEL}")
                out, err=_call_llm([
                    {"role":"system","content":"You extract metadata for naming scanned documents and output strict JSON only."},
                    {"role":"user","content":content}
                ], max_tokens=450, timeout=lm_timeout, retries=lm_retries)
                if out:
                    data=_extract_json_loose(out)
                    if data:
                        _postprocess_llm_info(data)
                        return data
                    return None
                _progress(f"  LLM (vision) no result in {_fmt_secs(time.monotonic()-t0)}")
                if not _is_context_overflow(err):
                    _progress(f"  vision stopped: {str(err)[:200]}")
                    return None
            return None

        # --- Text-first path
        if len(text) >= MIN_TEXT_CHARS:
            budgets=[7000, 4500, 2800, 1600]
            for idx, b in enumerate(budgets, start=1):
                _progress(f"[3/4] Text pass {idx}/{len(budgets)}: budget={b}")
                t=_compact_text(text, b)
                t0=time.monotonic()
                _progress(f"  calling LLM (text) model={LLM_MODEL}")
                out, err=_call_llm([
                    {"role":"system","content":"You extract metadata for naming scanned documents and output strict JSON only."},
                    {"role":"user","content":_prompt_from_text(t, keywords_count=keywords_count)}
                ], max_tokens=350, timeout=lm_timeout, retries=lm_retries)

                if out:
                    data=_extract_json_loose(out)
                    if not data: return None, text

                    _progress(f"  text parse ok in {_fmt_secs(time.monotonic()-t0)}")

                    # NEW: if too many unknowns, force vision and merge
                    if _unknown_count(data) >= 2:
                        _progress("  too many unknowns; trying vision merge")
                        v=_vision_extract(partial_hint=data)
                        if v: data=_merge_fill_missing(data, v)

                    _postprocess_llm_info(data)

                    return data, text

                if not _is_context_overflow(err):
                    _progress(f"  text stopped: {str(err)[:200]}")
                    return None, text
                _progress("  context overflow; reducing budget")

        # --- Vision fallback (no/low text or persistent overflow)
        _progress("[3/4] Falling back to vision")
        v=_vision_extract(partial_hint=None)
        if v:
            _postprocess_llm_info(v)
            return v, text
        return None, text
    finally:
        if repair_ctx is not None:
            repair_ctx.cleanup()

def create_filename(info: typing.Dict[str, typing.Any]) -> str:
    d=_normalize_date(info.get("date"))
    if not d: d="UnknownDate"
    provider=_safe_filename(info.get("provider") or "Unknown Provider", 60)
    dt=_normalize_doc_type(info.get("document_type")) or "Document"
    title=_safe_filename(info.get("title") or "Untitled", 80)

    parts=[d, provider, dt, title]
    parts=[p for p in parts if p and p.strip()]
    base=" - ".join(parts).strip()
    base=_safe_filename(base, 180)
    return f"{base}.pdf"

def pretty_title_from_filename(dst_basename: str) -> str:
    s=os.path.basename(str(dst_basename or "")).strip()
    if s.lower().endswith(".pdf"): s=s[:-4]
    parts=[p.strip() for p in s.split(" - ")]
    connectors=set(["a","an","the","and","or","of","to","for","in"])
    date_rx=re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")
    caps_rx=re.compile(r"^[A-Z]{2,6}$")

    out=[]
    for part in parts:
        if not part: continue
        words=[w for w in part.split() if w]
        if not words: continue
        first_word=True
        new_words=[]
        for w in words:
            if date_rx.match(w):
                new_words.append(w)
            elif caps_rx.match(w):
                new_words.append(w)
            else:
                low=w.lower()
                if (not first_word) and (low in connectors):
                    new_words.append(low)
                else:
                    new_words.append((w[:1].upper()+w[1:].lower()) if w else w)
            if first_word: first_word=False
        out.append(" ".join(new_words))
    return " - ".join(out).strip()

def pdf_creation_date_from_ymd(ymd: typing.Optional[str]) -> typing.Optional[str]:
    d=_normalize_date(ymd)
    if not d: return None
    try:
        dt=datetime.strptime(str(d).strip(), "%Y-%m-%d")
    except Exception:
        return None
    return f"D:{dt.strftime('%Y%m%d')}000000Z"

def format_keywords(keywords: typing.List[str], keywords_count: int) -> typing.Optional[str]:
    try:
        n=int(keywords_count)
    except Exception:
        return None
    if n <= 0: return None
    seen=set()
    out=[]
    for kw in (keywords or []):
        if not isinstance(kw, str): continue
        kw=kw.strip()
        if not kw: continue
        if kw in seen: continue
        seen.add(kw)
        out.append(kw)
        if len(out) >= n: break
    if not out: return None
    return "; ".join(out)

def _pdf_appears_signed(reader) -> bool:
    def _resolve(o):
        try:
            return o.get_object()
        except Exception:
            return o

    def _is_sig_field(d):
        if not (hasattr(d, "get") and callable(getattr(d, "get"))):
            return False
        ft=d.get("/FT")
        if str(ft) == "/Sig":
            return True
        v=_resolve(d.get("/V"))
        if (hasattr(v, "get") and callable(getattr(v, "get"))) and str(v.get("/Type")) == "/Sig":
            return True
        return False

    try:
        root=_resolve(reader.trailer.get("/Root"))
        acro=_resolve(root.get("/AcroForm")) if (hasattr(root, "get") and callable(getattr(root, "get"))) else None
        fields=_resolve(acro.get("/Fields")) if (hasattr(acro, "get") and callable(getattr(acro, "get"))) else None
        if isinstance(fields, list):
            stack=list(fields)
            seen=set()
            while stack:
                f=_resolve(stack.pop())
                oid=id(f)
                if oid in seen: continue
                seen.add(oid)
                if _is_sig_field(f):
                    return True
                if hasattr(f, "get") and callable(getattr(f, "get")):
                    kids=_resolve(f.get("/Kids"))
                    if isinstance(kids, list):
                        stack.extend(kids)

        try:
            max_pages=50
            for i, page in enumerate(reader.pages):
                if i >= max_pages: break
                annots=_resolve(page.get("/Annots")) if (hasattr(page, "get") and callable(getattr(page, "get"))) else None
                if not isinstance(annots, list):
                    continue
                for a in annots:
                    ad=_resolve(a)
                    if not (hasattr(ad, "get") and callable(getattr(ad, "get"))):
                        continue
                    if str(ad.get("/Subtype")) != "/Widget":
                        continue
                    if _is_sig_field(ad):
                        return True
        except Exception:
            return True

        return False
    except Exception:
        return True

def write_pdf_metadata_in_place(dst_pdf_path: str, docinfo: typing.Dict[str, typing.Any]) -> typing.Tuple[bool, typing.Optional[str]]:
    try:
        from pypdf import PdfReader, PdfWriter
    except Exception:
        _progress("  metadata skipped: write_failed")
        return False, "write_failed"

    def _coerce_metadata(d):
        out={}
        for k,v in (d or {}).items():
            if v is None: continue
            if not isinstance(k, str): continue
            if not k.startswith("/"):
                continue
            if isinstance(v, bytes):
                try:
                    v=v.decode("utf-8", "replace")
                except Exception:
                    v=str(v)
            else:
                v=str(v)
            v=v.strip()
            if not v: continue
            out[k]=v
        return out

    meta=_coerce_metadata(docinfo)
    if not meta:
        _progress("  metadata skipped: no_metadata")
        return False, "no_metadata"

    tmp_path=None
    try:
        dst_pdf_path=os.path.abspath(dst_pdf_path)
        dst_dir=os.path.dirname(dst_pdf_path) or "."

        with open(dst_pdf_path, "rb") as f_in:
            reader=PdfReader(f_in)

            if getattr(reader, "is_encrypted", False):
                try:
                    reader.decrypt("")
                except Exception:
                    _progress("  metadata skipped: encrypted")
                    return False, "encrypted"
                try:
                    _=reader.pages[0]
                except Exception:
                    _progress("  metadata skipped: encrypted")
                    return False, "encrypted"

            if _pdf_appears_signed(reader):
                _progress("  metadata skipped: signed")
                return False, "signed"

            try:
                writer=PdfWriter(clone_from=reader)
            except Exception:
                writer=PdfWriter(clone_from=dst_pdf_path)

            writer.add_metadata(meta)

            fd, tmp_path=tempfile.mkstemp(prefix=".scanfile_meta_", suffix=".pdf", dir=dst_dir)
            os.close(fd)
            try:
                try:
                    os.chmod(tmp_path, os.stat(dst_pdf_path).st_mode & 0o777)
                except Exception:
                    pass

                with open(tmp_path, "wb") as f_out:
                    writer.write(f_out)
                os.replace(tmp_path, dst_pdf_path)
                tmp_path=None
                return True, None
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
    except Exception:
        _progress("  metadata skipped: write_failed")
        return False, "write_failed"

def _positive_int(s):
    try:
        v=int(s)
    except Exception:
        raise argparse.ArgumentTypeError("must be an integer")
    if v <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return v

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("pdf", help="Path to input PDF")
    ap.add_argument("--outdir", default=None, help="Destination directory (default: <input_dir>/processed)")
    ap.add_argument("--move", action="store_true", help="Move instead of copy")
    ap.add_argument("--metadata-only", action="store_true", help="Write PDF DocumentInfo metadata in-place (no copy/move)")
    ap.add_argument("--dry-run", action="store_true", help="Print result, do not write file")
    ap.add_argument("--print-json", action="store_true", help="Print extracted JSON")
    ap.add_argument("--no-progress", action="store_true", help="Disable progress output")
    ap.add_argument("--no-repair", action="store_true", help="Disable qpdf/ghostscript repair attempts")
    ap.add_argument("--keywords-count", type=_positive_int, default=5, help="Number of keywords to include (default: 5)")
    ap.add_argument("--lm-timeout", type=int, default=LLM_TIMEOUT, help="LLM timeout in seconds")
    ap.add_argument("--lm-retries", type=int, default=LLM_MAX_RETRIES, help="LLM max retries on network/server errors")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args=ap.parse_args()

    global _PROGRESS_ENABLED
    _PROGRESS_ENABLED = (not args.no_progress)
    if args.print_json and (not sys.stdout.isatty()) and (not _PROGRESS_FORCE):
        # Keep stdout machine-readable when piping JSON.
        _PROGRESS_ENABLED=False

    pdf_input=args.pdf
    if not os.path.isfile(pdf_input):
        print("File not found:", pdf_input)
        return 2

    if args.metadata_only:
        if args.outdir is not None:
            print("Error: --metadata-only is incompatible with --outdir")
            return 2
        if args.move:
            print("Error: --metadata-only is incompatible with --move")
            return 2

        if args.dry_run and (not _PROGRESS_FORCE):
            _PROGRESS_ENABLED=False

        try:
            lm_timeout=max(1, int(args.lm_timeout))
            lm_retries=max(0, int(args.lm_retries))
            info, raw_text=extract_information(pdf_input, lm_timeout=lm_timeout, lm_retries=lm_retries, allow_repair=(not args.no_repair), keywords_count=args.keywords_count)
        except RuntimeError as e:
            print("Failed to process PDF:", str(e))
            print("Hint: the PDF may be corrupt; installing qpdf/ghostscript can sometimes repair it.")
            return 1
        if (not info) and raw_text:
            _progress("[4/4] Falling back to heuristic extraction")
            info=_heuristic_extract(raw_text)

        if not info:
            print("Failed to extract information.")
            return 1

        if args.print_json and (not args.dry_run):
            print(json.dumps(info, indent=2, ensure_ascii=False))

        title=pretty_title_from_filename(os.path.basename(pdf_input))
        docinfo={
            "/Title": title,
            "/Author": info.get("author") or info.get("provider"),
            "/Subject": info.get("subject"),
            "/Keywords": format_keywords(info.get("keywords", []), args.keywords_count),
        }
        creation_date=pdf_creation_date_from_ymd(info.get("date"))
        if creation_date:
            docinfo["/CreationDate"]=creation_date
            docinfo["/ModDate"]=creation_date

        if args.dry_run:
            print(json.dumps(docinfo, indent=2, ensure_ascii=False))
            return 0

        progress_prev=_PROGRESS_ENABLED
        try:
            _PROGRESS_ENABLED=False
            ok, reason=write_pdf_metadata_in_place(pdf_input, docinfo)
        finally:
            _PROGRESS_ENABLED=progress_prev
        if not ok:
            print(reason or "write_failed")
            return 1
        return 0

    _progress(f"Processing: {os.path.basename(pdf_input)}")

    original_dir=os.path.dirname(os.path.abspath(pdf_input))
    outdir=args.outdir or os.path.join(original_dir, "processed")
    os.makedirs(outdir, exist_ok=True)
    _progress(f"Output dir: {outdir}")

    try:
        lm_timeout=max(1, int(args.lm_timeout))
        lm_retries=max(0, int(args.lm_retries))
        info, raw_text=extract_information(pdf_input, lm_timeout=lm_timeout, lm_retries=lm_retries, allow_repair=(not args.no_repair), keywords_count=args.keywords_count)
    except RuntimeError as e:
        print("Failed to process PDF:", str(e))
        print("Hint: the PDF may be corrupt; installing qpdf/ghostscript can sometimes repair it.")
        return 1
    if not info and raw_text:
        _progress("[4/4] Falling back to heuristic extraction")
        info=_heuristic_extract(raw_text)

    if not info:
        print("Failed to extract information.")
        return 1

    if args.print_json:
        print(json.dumps(info, indent=2, ensure_ascii=False))

    new_name=create_filename(info)
    dst=_unique_path(os.path.join(outdir, new_name))

    print("Proposed:", os.path.basename(dst))
    if args.dry_run: return 0

    docinfo={
        "/Title": pretty_title_from_filename(os.path.basename(dst)),
        "/Author": info.get("author") or info.get("provider"),
        "/Subject": info.get("subject"),
        "/Keywords": format_keywords(info.get("keywords", []), args.keywords_count),
    }
    creation_date=pdf_creation_date_from_ymd(info.get("date"))
    if creation_date:
        docinfo["/CreationDate"]=creation_date
        docinfo["/ModDate"]=creation_date

    if args.move:
        _progress("[4/4] Moving file")
        shutil.move(pdf_input, dst)
        try:
            write_pdf_metadata_in_place(dst, docinfo)
        except Exception:
            _progress("  metadata skipped: write_failed")
        print("Moved to:", dst)
    else:
        _progress("[4/4] Copying file")
        shutil.copy2(pdf_input, dst)
        try:
            write_pdf_metadata_in_place(dst, docinfo)
        except Exception:
            _progress("  metadata skipped: write_failed")
        print("Copied to:", dst)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
