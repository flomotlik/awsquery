#!/usr/bin/env python3
"""Static shape-aware audit of default_filters.yaml.

Walks every ``$``-suffix entry, looks up the service+operation shape via
``ShapeCache``, simulates the same flattening the formatter applies
(``transform_tags_structure`` + ``flatten_dict_keys``), and classifies each
entry as correct, broken, kv_dyn, wildcard, or unverified. Returns a dict
suitable for CI regression checks. The heuristic has documented false
positives (e.g. ``value$`` on list-of-primitive data fields); manual review
of the ``broken`` list is required before acting on it.
"""

import os
import sys

import yaml

import awsquery
from awsquery.shapes import ShapeCache


def _detect_kv_bases(simp):
    bases = set()
    by_lower = {k.lower(): k for k in simp}
    for k, t in simp.items():
        if not k.lower().endswith(".key") or t != "string":
            continue
        base_l = k.lower()[:-4]
        val_l = f"{base_l}.value"
        if val_l in by_lower and simp[by_lower[val_l]] == "string":
            bases.add(k[:-4])
    return bases


def _detect_list_of_primitive(simp):
    return {
        k
        for k, t in simp.items()
        if t == "list" and not any(c.startswith(f"{k}.") for c in simp)
    }


def _kv_endings(kv_bases):
    out = set()
    for kb in kv_bases:
        parts = kb.split(".")
        for i in range(len(parts)):
            out.add(".".join(parts[i:]).lower())
    return out


def audit_default_filters(config_path=None):
    if config_path is None:
        config_path = os.path.join(
            os.path.dirname(awsquery.__file__), "default_filters.yaml"
        )
    sc = ShapeCache()
    with open(config_path) as f:
        cfg = yaml.safe_load(f) or {}
    report = {
        "broken": [],
        "correct": [],
        "wildcard": [],
        "kv_dyn": [],
        "unverified": [],
    }

    for svc, actions in cfg.items():
        if not isinstance(actions, dict):
            continue
        for op, opcfg in actions.items():
            if not isinstance(opcfg, dict):
                continue
            cols = opcfg.get("columns", []) or []
            op_dash = op.replace("_", "-")
            try:
                _, simp, _ = sc.get_response_fields(svc, op_dash)
            except Exception as e:
                for col in cols:
                    if col.endswith("$") and not col.startswith("^"):
                        report["unverified"].append(
                            (svc, op, col, f"shape err: {type(e).__name__}")
                        )
                continue
            if not simp:
                for col in cols:
                    if col.endswith("$") and not col.startswith("^"):
                        report["unverified"].append((svc, op, col, "empty shape"))
                continue
            if simp.get("*") == "map-wildcard":
                for col in cols:
                    if col.endswith("$") and not col.startswith("^"):
                        report["wildcard"].append((svc, op, col))
                continue

            kv_bases = _detect_kv_bases(simp)
            list_prim = _detect_list_of_primitive(simp)
            list_prim_lower = {p.lower() for p in list_prim}
            kv_drop_lower = {f"{kb.lower()}.key" for kb in kv_bases} | {
                f"{kb.lower()}.value" for kb in kv_bases
            }
            post_keys = {
                k
                for k in simp
                if k.lower() not in kv_drop_lower and k.lower() not in list_prim_lower
            }
            kv_endings = _kv_endings(kv_bases)

            top_list_primitive = simp.get("value") == "list"

            for col in cols:
                if not col.endswith("$") or col.startswith("^"):
                    continue
                base = col[:-1]
                bl = base.lower()
                if "." in base:
                    lhs = base.rsplit(".", 1)[0].lower()
                    lhs0 = base.split(".", 1)[0].lower()
                    if (
                        any(lhs == e or lhs.endswith("." + e) for e in kv_endings)
                        or lhs0 in kv_endings
                    ):
                        report["kv_dyn"].append((svc, op, col))
                        continue
                if top_list_primitive and bl == "value":
                    report["correct"].append((svc, op, col, ["<top-level list-of-primitive>"]))
                    continue
                matches = [k for k in post_keys if k.lower().endswith(bl)]
                if not matches:
                    if bl in list_prim_lower:
                        report["broken"].append(
                            (svc, op, col, f"list-of-primitive -> flattens to {base}.0..N")
                        )
                    else:
                        report["broken"].append((svc, op, col, "no key ends with"))
                    continue
                if bl in kv_endings:
                    report["broken"].append(
                        (
                            svc,
                            op,
                            col,
                            f"target IS K/V base -> post-transform {base}.<dyn> only",
                        )
                    )
                    continue
                report["correct"].append((svc, op, col, matches[:3]))

    return report


def main():
    r = audit_default_filters()
    print(
        f"Broken: {len(r['broken'])}, "
        f"Correct: {len(r['correct'])}, "
        f"K/V dyn: {len(r['kv_dyn'])}, "
        f"Wildcard: {len(r['wildcard'])}, "
        f"Unverified: {len(r['unverified'])}"
    )
    for entry in r["broken"]:
        svc, op, col, reason = entry
        print(f"  BROKEN  {svc}.{op:50} : {col:35}  -- {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
