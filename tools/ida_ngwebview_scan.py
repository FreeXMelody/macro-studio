import json
import os

import ida_auto
import ida_bytes
import ida_funcs
import ida_hexrays
import ida_kernwin
import ida_name
import ida_nalt
import ida_segment
import ida_ua
import ida_xref
import idautils
import idc


KEYWORDS = [
    "unisdk_js_native_call",
    "NGWebViewOpenURL",
    "NGWebViewClose",
    "NGWebviewClearCache",
    "NGWebviewShow",
    "NGWebViewControl",
    "openBrowser",
    "ngwebview_notify_native",
    "closeWebView",
    "methodId",
    "reqData",
    "webURL",
    "URLString",
    "customJS",
    "RegisterJsBridgeHandlers",
    "ExecuteJavaScript",
    "CreateWebview",
    "workId_",
    "action-station",
]


def text_at(ea, max_len=256):
    s = ida_bytes.get_strlit_contents(ea, -1, ida_nalt.STRTYPE_C)
    if s is None:
        s = ida_bytes.get_strlit_contents(ea, -1, ida_nalt.STRTYPE_C_16)
    if s is None:
        return ""
    try:
        return s.decode("utf-8", errors="replace")[:max_len]
    except Exception:
        return repr(s[:max_len])


def func_info(ea):
    fn = ida_funcs.get_func(ea)
    if not fn:
        return None
    name = ida_funcs.get_func_name(fn.start_ea)
    return {"start": hex(fn.start_ea), "end": hex(fn.end_ea), "name": name}


def xrefs_to(ea, limit=50):
    refs = []
    for xr in idautils.XrefsTo(ea):
        refs.append(
            {
                "from": hex(xr.frm),
                "type": int(xr.type),
                "func": func_info(xr.frm),
            }
        )
        if len(refs) >= limit:
            break
    return refs


def disasm_window(ea, count=40):
    out = []
    cur = ea
    for _ in range(count):
        out.append({"ea": hex(cur), "text": idc.generate_disasm_line(cur, 0)})
        cur = idc.next_head(cur)
        if cur == idc.BADADDR:
            break
    return out


def decompile_func(start_ea):
    if not ida_hexrays.init_hexrays_plugin():
        return None
    try:
        cfunc = ida_hexrays.decompile(start_ea)
        if not cfunc:
            return None
        lines = []
        for line in str(cfunc).splitlines()[:180]:
            lines.append(ida_lines.tag_remove(line) if "ida_lines" in globals() else line)
        return "\n".join(lines)
    except Exception as exc:
        return "DECOMPILE_ERROR: %s" % exc


def main():
    ida_auto.auto_wait()

    strings = []
    for s in idautils.Strings():
        value = str(s)
        for keyword in KEYWORDS:
            if keyword.lower() in value.lower():
                strings.append(
                    {
                        "ea": hex(s.ea),
                        "keyword": keyword,
                        "value": value[:300],
                        "xrefs": xrefs_to(s.ea),
                    }
                )
                break

    function_starts = []
    for item in strings:
        for ref in item["xrefs"]:
            if ref["func"] and ref["func"]["start"] not in function_starts:
                function_starts.append(ref["func"]["start"])

    functions = []
    for start_hex in function_starts[:80]:
        start = int(start_hex, 16)
        functions.append(
            {
                "func": func_info(start),
                "disasm": disasm_window(start, 80),
                "pseudo": decompile_func(start),
            }
        )

    imports = []
    for i in range(ida_nalt.get_import_module_qty()):
        modname = ida_nalt.get_import_module_name(i) or ""

        def cb(ea, name, ordinal):
            if name and any(k.lower() in name.lower() for k in KEYWORDS):
                imports.append(
                    {
                        "module": modname,
                        "ea": hex(ea),
                        "name": name,
                        "ordinal": ordinal,
                        "xrefs": xrefs_to(ea),
                    }
                )
            return True

        ida_nalt.enum_import_names(i, cb)

    out = {
        "input": ida_nalt.get_input_file_path(),
        "segments": [
            {
                "name": ida_segment.get_segm_name(seg),
                "start": hex(seg.start_ea),
                "end": hex(seg.end_ea),
            }
            for seg in idautils.Segments()
        ],
        "strings": strings,
        "imports": imports,
        "functions": functions,
    }

    out_path = os.environ.get("IDA_NGWEBVIEW_SCAN_OUT")
    if not out_path:
        out_path = os.path.join(os.getcwd(), "ngwebview_ida_scan.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("WROTE", out_path)
    ida_kernwin.qexit(0)


main()
