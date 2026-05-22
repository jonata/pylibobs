"""
Regenerate pylibobs/_declarations_auto.py from libobs's headers.

Walks libobs's headers, extracts every EXPORTed function, normalises the
signature for cffi cdef(), and emits one big string plus a "typedef wall"
that declares every opaque type referenced.

Usage:
    cd <repo root>
    # Download + extract libobs source under obs-studio-<ver>/
    python scripts/generate_cdef.py [obs-studio-<ver>/libobs]
"""

from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
HEADERS_ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "obs-studio-32.1.2" / "libobs"
DLL = ROOT / "pylibobs/_libs/windows/x86_64/obs.dll"


def list_dll_exports() -> set[str]:
    data = DLL.read_bytes()
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    coff_off = e_lfanew + 4
    opt_off = coff_off + 20
    opt_size = struct.unpack_from("<H", data, coff_off + 16)[0]
    export_rva, _ = struct.unpack_from("<II", data, opt_off + 112)
    n_sec = struct.unpack_from("<H", data, coff_off + 2)[0]
    sec_off = opt_off + opt_size
    sections = []
    for i in range(n_sec):
        s = sec_off + i * 40
        vs, va, _, rp = struct.unpack_from("<IIII", data, s + 8)
        sections.append((va, vs, rp))
    def rva2off(rva):
        for v, vs, rp in sections:
            if v <= rva < v + vs: return rp + (rva - v)
    exp_off = rva2off(export_rva)
    n_names, _, addr_names, _ = struct.unpack_from("<IIII", data, exp_off + 24)
    names_off = rva2off(addr_names)
    out = set()
    for i in range(n_names):
        rva = struct.unpack_from("<I", data, names_off + i * 4)[0]
        off = rva2off(rva)
        end = data.find(b"\0", off)
        out.add(data[off:end].decode("ascii", errors="replace"))
    return out


FUNC_RE = re.compile(
    r"""
    EXPORT\s+
    (?P<ret>[\w\s\*\(\)]+?)
    \s+(?P<name>[A-Za-z_]\w*)
    \s*\(
    (?P<args>[^;]*?)
    \)\s*;
    """,
    re.VERBOSE | re.DOTALL,
)

def strip_comments(s):
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", s)

def collapse(s):
    return re.sub(r"\s+", " ", s).strip()

NOISE = ["OBS_DEPRECATED", "OBS_EXTERNAL_DEPRECATED", "OBS_NORETURN"]

def clean_decl(ret, name, args):
    ret = strip_comments(ret); args = strip_comments(args)
    for noise in NOISE:
        ret = ret.replace(noise, ""); args = args.replace(noise, "")
    ret = collapse(ret); args = collapse(args)
    if args == "": args = "void"
    if "(*" in ret or "(*" in name: return None
    return f"{ret} {name}({args});"

def extract_funcs(text):
    text = strip_comments(text)
    for m in FUNC_RE.finditer(text):
        name = m.group("name")
        decl = clean_decl(m.group("ret"), name, m.group("args"))
        if decl: yield name, decl


CKW = {"void","char","short","int","long","float","double","signed","unsigned",
       "const","volatile","restrict","_Bool","bool","uint8_t","uint16_t",
       "uint32_t","uint64_t","int8_t","int16_t","int32_t","int64_t","size_t",
       "ssize_t","ptrdiff_t","intptr_t","uintptr_t","wchar_t","FILE","va_list",
       "Py_ssize_t","struct","enum","union","typedef"}

ALREADY_TYPES = {
    "obs_source_t","obs_scene_t","obs_sceneitem_t","obs_output_t",
    "obs_encoder_t","obs_service_t","obs_data_t","obs_data_array_t",
    "obs_properties_t","obs_property_t","signal_handler_t","proc_handler_t",
    "obs_display_t","obs_hotkey_id","obs_hotkey_t","obs_fader_t",
    "obs_volmeter_t","obs_key_t","obs_key_combination_t","obs_hotkey_func",
    "obs_volmeter_updated_t","obs_fader_changed_t","obs_enum_source_cb_t",
    "obs_enum_audio_devices_cb_t","video_t","audio_t","gs_texture_t",
    "gs_swapchain_t","calldata_t","signal_callback_t","obs_data_item_t",
    "obs_source_audio_capture_t","audio_output_callback_t",
    "raw_video_callback_t","obs_render_callback_t","obs_tick_callback_t",
    "obs_source_enum_filters_cb_t","obs_source_enum_proc_t",
    "obs_encoder_roi_cb_t","obs_output_packet_cb_t",
    "obs_display_draw_callback_t","obs_load_source_cb","obs_hotkey_enum_func",
}
ALREADY_STRUCTS = {
    "obs_video_info","obs_audio_info","gs_window","gs_init_data","calldata",
    "obs_key_combination","vec2","video_data","audio_data","video_scale_info",
    "obs_transform_info","obs_sceneitem_crop","obs_encoder_roi","encoder_packet",
}
ALREADY_ENUMS = {
    "obs_video_err","video_format","speaker_layout","obs_scale_type",
    "video_colorspace","video_range_type","obs_encoder_type","obs_output_flags",
    "gs_color_format","gs_zstencil_format","obs_transition_mode",
    "obs_peak_meter_type","obs_fader_type","obs_bounds_type",
    "obs_blending_method","obs_blending_type",
}


def collect_referenced_types(decls):
    structs, enums, typedefs = set(), set(), set()
    sre = re.compile(r"\bstruct\s+([A-Za-z_]\w*)")
    ere = re.compile(r"\benum\s+([A-Za-z_]\w*)")
    for line in decls:
        for m in sre.finditer(line): structs.add(m.group(1))
        for m in ere.finditer(line): enums.add(m.group(1))
    for hdr in sorted(HEADERS_ROOT.rglob("*.h")):
        try:
            text = strip_comments(hdr.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        for m in re.finditer(r"typedef\s+(?:[^;]+?)\b([A-Za-z_]\w*)\s*;", text):
            typedefs.add(m.group(1))
        for m in re.finditer(r"typedef\s+[^;]*?\(\s*\*\s*([A-Za-z_]\w*)\s*\)", text):
            typedefs.add(m.group(1))
    structs -= ALREADY_STRUCTS
    enums   -= ALREADY_ENUMS
    typedefs = (typedefs - ALREADY_TYPES) - CKW
    return structs, enums, typedefs


def main():
    if not HEADERS_ROOT.exists():
        sys.exit(f"Headers directory not found: {HEADERS_ROOT}\n"
                 "Download libobs source via:\n"
                 "  curl -L -o obs-source.tar.gz "
                 "https://github.com/obsproject/obs-studio/archive/refs/tags/<ver>.tar.gz\n"
                 "  tar -xzf obs-source.tar.gz")

    public = {e for e in list_dll_exports()
              if e.startswith(("obs_", "gs_", "signal_", "proc_", "calldata_",
                               "audio_output_", "video_output_"))}
    decls_text = (ROOT / "pylibobs" / "_declarations.py").read_text(encoding="utf-8")
    fre = re.compile(r"\b([A-Za-z_][\w]+)\s*\(")
    have = {m.group(1) for m in fre.finditer(decls_text)
            if m.group(1).startswith(("obs_","gs_","signal_","proc_","calldata_",
                                       "audio_output_","video_output_"))}
    missing = public - have

    found = {}
    for hdr in sorted(HEADERS_ROOT.rglob("*.h")):
        try: text = hdr.read_text(encoding="utf-8", errors="replace")
        except Exception: continue
        for name, decl in extract_funcs(text):
            if name in missing and name not in found:
                found[name] = decl

    structs, enums, typedefs = collect_referenced_types(list(found.values()))
    unfound = sorted(missing - found.keys())

    out_path = ROOT / "pylibobs" / "_declarations_auto.py"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write('"""Auto-generated cffi declarations for obs.dll. Do not edit."""\n\n')
        f.write('PREAMBLE = """\n')
        for s in sorted(structs):
            f.write(f"    struct {s};\n")
        for e in sorted(enums):
            f.write(f"    typedef int {e}_enum_stub; /* enum {e} */\n")
        for t in sorted(typedefs):
            base = t[:-2] if t.endswith("_t") else t
            f.write(f"    typedef struct {base}_s *{t};\n")
        f.write('"""\n\n')

        f.write('AUTO_DECLS = """\n')
        for name in sorted(found.keys()):
            f.write("    " + found[name] + "\n")
        f.write('"""\n\n')

        if unfound:
            f.write('STUB_DECLS = """\n')
            for n in unfound:
                f.write(f"    void {n}(void);\n")
            f.write('"""\n')
        else:
            f.write('STUB_DECLS = ""\n')

    print(f"Wrote {out_path}")
    print(f"  Total exports:        {len(public)}")
    print(f"  Already declared:     {len(have & public)}")
    print(f"  Sig auto-extracted:   {len(found)}")
    print(f"  Stubs:                {len(unfound)}")
    print(f"  Opaque structs:       {len(structs)}")
    print(f"  Opaque enums:         {len(enums)}")
    print(f"  Opaque typedefs:      {len(typedefs)}")


if __name__ == "__main__":
    main()
