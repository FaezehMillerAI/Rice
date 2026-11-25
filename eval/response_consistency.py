"""Bounded English checks between a prediction and its user-facing summary.

These rules use no gold labels or semantic model. Missing recognized wording is
reported as missing content, not proof of a semantic contradiction. ASK may omit
management actions; ANSWER must summarize the first cause and first action; ESC
must explicitly refer to a professional. Other structured items need not repeat.
"""

from __future__ import annotations

import re


RESPONSE_CONSISTENCY_VERSION = "v0.1"
_DIMENSIONS = ("status", "differential", "questions", "actions", "escalation")
_PROVISIONAL = r"\b(?:provisional|possible|possibly|may be|might be|could be|suspect|likely|consistent with|appears to be|suggests|not (?:a |yet )?confirmed)\b"
_PROFESSIONAL = r"\b(?:expert|specialist|pathologist|agronomist|plant doctor|extension (?:officer|agent|authority|service)|(?:plant |district )?clinic|professional (?:help|assessment))\b"
_REFERRAL = r"\b(?:contact|consult|call|visit|refer|submit|seek|assessment by|assessed by)\b"
_REQUEST = r"\b(?:please (?:check|inspect|observe|provide|describe|tell)|check whether|check if|inspect|observe|look for|tell me|provide more|describe|examine)\b"
_NEGATIVE_PREFIX = r"\b(?:do not|dont|never|avoid|should not|must not|need not|no need to|not necessary to)(?: \w+){0,3}$"
_QUESTION_GROUPS = {
    "q:q_lesion_margin": (r"lesions?|stripes?|spots?", r"tips?|margins?|edges?|wavy"),
    "q:q_older_vs_younger": (r"leaves|leaf", r"old(?:er|est)?|bottom|lower|lowest", r"yellow\w*|green|chlorosis"),
    "q:q_water_test": (r"water", r"cloudy|milky|ooze|stream\w*", r"cut|leaves|leaf|tissue|test"),
    "q:q_leaf_rolling": (r"leaves|leaf|blades?", r"roll\w*|curl\w*|fold\w*|tubes?|needles?"),
    "q:q_rewatering_recovery": (r"rain\w*|water\w*|irrigation", r"recover\w*|unroll\w*|uncurl\w*|healthy|normal"),
    "q:q_field_spatial_pattern": (r"field|plants?", r"patch\w*|uniform\w*|whole|entire|evenly|groups?"),
    "q:q_blast_spindle_lesion": (r"lesions?|spots?", r"diamonds?|spindle|eyes", r"gr[ae]y|white|whitish|cent[er]+"),
    "q:q_brown_spot_shape": (r"spots?|lesions?", r"oval|round|circular|sesame", r"brown|yellow|halo|ring"),
    "q:q_neck_rot": (r"neck|stem|panicle", r"black\w*|broken|rot\w*|whiteheads"),
}
_ACTION_LABELS = {
    "action:avoid_excess_nitrogen": ["Avoid excess nitrogen", "Avoid excessive nitrogen"],
    "action:ensure_field_drainage": ["Ensure field drainage"],
    "action:balanced_fertilizer_split": ["Use balanced split fertilizer applications"],
    "action:alternate_wetting_drying": ["Use alternate wetting and drying"],
    "action:use_resistant_varieties": ["Use resistant varieties"],
    "action:use_blast_resistant_varieties": ["Use blast resistant varieties"],
    "action:improve_soil_fertility": ["Improve soil fertility"],
    "action:certified_clean_treated_seed": ["Use clean certified treated seed"],
    "action:escalate_to_pathologist": ["Refer the case to a plant pathologist"],
}


def _norm(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value).casefold().replace("’", "'").replace("'", "")).strip()


def _ids(value):
    return list(dict.fromkeys(item for item in value if isinstance(item, str) and item.strip())) if isinstance(value, list) else []


def _contains(text, phrase):
    return bool(phrase and re.search(r"\b" + re.escape(_norm(phrase)) + r"\b", _norm(text)))


def _clauses(text):
    return [piece.strip() for part in re.findall(r"[^.!?;\n]+[.!?;]?", text)
            for piece in re.split(r"\b(?:but|however)\b", part, flags=re.I) if piece.strip()]


def _request(clause):
    normalized = _norm(clause)
    if re.search(r"\b(?:do not|dont|never|avoid) (?:check|inspect|observe|ask|examine)\b", normalized):
        return False
    return bool(re.search(_REQUEST, normalized) or (
        clause.rstrip().endswith("?") and re.match(r"^(?:\d+ )?(?:are|is|do|does|did|have|has|can|could|what|which|when|where|how)\b", normalized)
    ))


def _certainty(clause):
    if clause.rstrip().endswith("?") and re.match(r"^(?:are|is|do|does|can|could|what|which)\b", _norm(clause)):
        return False
    text = _norm(clause)
    text = re.sub(r"\b(?:not|no|never|not yet|cannot be|has not been) (?:a |yet )?(?:confirmed|certain|definitive|definitely|100 percent)\b", "", text)
    return bool(re.search(r"\b(?:confirmed|definitely|certainly|100 percent|definitive diagnosis|without doubt)\b", text) or (
        re.search(r"100\s*%", clause) and not re.search(r"\bnot\s+100\s*%", clause, re.I)
    ))


def _referrals(clauses):
    current, conditional, rejected = [], [], []
    for clause in clauses:
        text = _norm(clause)
        if not (re.search(_PROFESSIONAL, text) and re.search(_REFERRAL, text)):
            continue
        negative_text = text.replace("do not hesitate to", "please")
        negative = re.search(r"\b(?:do not|dont|never|avoid|no need to|not necessary to|need not|should not|must not)(?: \w+){0,3} (?:contact|consult|seek|visit|call|refer)\b", negative_text)
        if negative or re.search(r"\b(?:not required|not necessary|unnecessary|not needed)\b", negative_text):
            rejected.append(clause)
        elif re.search(r"\b(?:if|unless|when|as needed)\b", text):
            conditional.append(clause)
        else:
            current.append(clause)
    return current, conditional, rejected


def _check(applicable, score, reason, *, matched=(), conflicts=(), **details):
    state = "not_applicable" if not applicable else "unassessed" if score is None else "passed" if score == 1 else "failed" if score == 0 else "partial"
    return {"applicable": applicable, "score": score, "state": state, "reason": reason,
            "matched_spans": list(matched), "conflict_spans": list(conflicts), **details}


def _cause_aliases(causes, predicted):
    records = causes if isinstance(causes, dict) else {}
    result = {}
    for cause_id in dict.fromkeys([*records, *predicted]):
        if not isinstance(cause_id, str):
            continue
        row = records.get(cause_id, {})
        row = row if isinstance(row, dict) else {}
        humanized = cause_id.split(":")[-1].replace("_", " ")
        aliases = [cause_id]
        if len(humanized.split()) > 1 or (len(humanized) >= 5 and humanized not in {"unknown", "other", "unspecified", "none"}):
            aliases.append(humanized)
        aliases.extend(row.get(field) for field in ("canonical_name", "display_name", "skos_pref_label"))
        alternate = row.get("skos_alt_labels", [])
        aliases.extend(alternate.split("|") if isinstance(alternate, str) else alternate if isinstance(alternate, list) else [])
        result[cause_id] = [alias for alias in aliases if isinstance(alias, str) and alias.strip()]
    return result


def _cause_check(text, clauses, predicted, causes, status):
    if status == "provisional_assessment" and not predicted:
        return _check(True, 0.0, "missing_structured_candidate", required_ids=[], matched_ids=[], candidate_ids=[])
    aliases = _cause_aliases(causes, predicted)
    hits, conflicts = set(), []
    for clause in clauses:
        normalized = _norm(clause)
        for cause_id, labels in aliases.items():
            for label in labels:
                if not _contains(clause, label):
                    continue
                alias = re.escape(_norm(label))
                negated = re.search(r"\b(?:not (?:a case of |caused by |due to )?|no evidence of |ruled out |excluded )" + alias + r"\b", normalized) or re.search(r"\b" + alias + r" (?:is|has been) (?:ruled out|excluded|absent|not present|not (?:the |a )?cause|not likely|unlikely)\b", normalized)
                if cause_id in predicted:
                    if not negated:
                        hits.add(cause_id)
                    elif not _request(clause):
                        conflicts.append(clause)
                elif not negated:
                    assessment = re.search(r"\b(?:cause|including|diagnosis|diagnosed|assessment|consistent with|likely|possible|potential|suspect|may be|could be|this is|it is)\b", normalized)
                    if assessment and not _request(clause):
                        conflicts.append(clause)
    required = predicted[:1] if status == "provisional_assessment" else []
    if required and aliases.get(required[0]) == [required[0]] and required[0] not in hits and not conflicts:
        return _check(True, None, "cause_aliases_unavailable", required_ids=required, matched_ids=[], candidate_ids=predicted)
    applicable = bool(required or conflicts or hits)
    score = 0.0 if conflicts else float(bool(required[0] in hits)) if required else 1.0 if hits else None
    reason = "contradiction" if conflicts else "required_first_candidate_present" if required and score else "missing_first_candidate" if required else "optional_candidate_mentions_agree" if hits else "candidate_summary_optional"
    return _check(applicable, score, reason, matched=list(dict.fromkeys(clause for clause in clauses for cid in sorted(hits) if any(_contains(clause, label) for label in aliases[cid]))),
                  conflicts=conflicts, required_ids=required, matched_ids=sorted(hits), candidate_ids=predicted)


def _question_check(clauses, predicted, questions, status):
    if status != "needs_more_information":
        return _check(False, None, "questions_optional_for_this_status")
    records = questions if isinstance(questions, dict) else {}
    requests = [clause for clause in clauses if _request(clause)]
    hits, unknown, spans = [], [], []
    for question_id in predicted:
        row = records.get(question_id, {})
        row = row if isinstance(row, dict) else {}
        labels = [row.get(key) for key in ("canonical_text", "farmer_friendly_phrasing", "question", "text")]
        labels = [label for label in labels if isinstance(label, str) and label.strip()]
        groups = _QUESTION_GROUPS.get(question_id)
        if not labels and groups is None:
            unknown.append(question_id)
            continue
        matched = [clause for clause in requests if any(_contains(clause, label) for label in labels) or (
            groups is not None and all(re.search(r"\b(?:" + group + r")\b", _norm(clause)) for group in groups)
        )]
        if matched:
            hits.append(question_id)
            spans.extend(matched)
    score = len(hits) / len(predicted) if predicted and len(unknown) < len(predicted) else None if unknown else 0.0
    reason = "question_coverage" if hits else "question_ids_unavailable" if unknown else "missing_specific_questions"
    return _check(True, score, reason, matched=list(dict.fromkeys(spans)), required_ids=predicted,
                  matched_ids=hits, unmatched_ids=[qid for qid in predicted if qid not in hits], unassessed_ids=unknown)


def build_action_catalog(engine):
    """Read existing management metadata only; never retrieve or diagnose a case."""
    getter = getattr(engine, "get_management_actions", None)
    if not callable(getter):
        return {}
    diseases = getattr(engine, "diseases", {})
    cause_ids = list(diseases) if isinstance(diseases, dict) else []
    catalog = {}
    for cause_id, escalated in [*((key, False) for key in cause_ids), ("", False), ("", True)]:
        rows = getter(cause_id, escalated)
        for row in rows if isinstance(rows, (list, tuple)) else []:
            if isinstance(row, dict) and isinstance(row.get("action_id"), str) and isinstance(row.get("action"), str):
                texts = catalog.setdefault(row["action_id"], [])
                if row["action"] not in texts:
                    texts.append(row["action"])
    return catalog


def _action_check(text, clauses, actions, catalog, status):
    catalog = catalog if isinstance(catalog, dict) else {}
    conflicts = []
    avoid_nitrogen = any("avoid_excess_nitrogen" in action or re.search(r"\b(?:avoid|reduce|limit).{0,30}nitrogen\b", _norm(action)) for action in actions)
    if avoid_nitrogen:
        for clause in clauses:
            normalized = _norm(clause)
            for recommendation in re.finditer(r"\b(?:apply|add|use|give) (?:more|excess(?:ive)?|high(?: doses? of)?) nitrogen\b|\bincrease (?:the )?nitrogen (?:application|dosage|levels)\b", normalized):
                prefix = normalized[:recommendation.start()].replace("do not hesitate to", "please").strip()
                if not re.search(r"\b(?:do not|dont|never|avoid|should not|must not)(?: ever)?$", prefix):
                    conflicts.append(clause)
    required = actions[:1] if status == "provisional_assessment" else []
    matched = []
    unavailable = []
    for action in actions:
        if action.startswith("action:"):
            texts = catalog.get(action, [])
            texts = [texts] if isinstance(texts, str) else texts if isinstance(texts, list) else []
            if not texts:
                unavailable.append(action)
                continue
            texts = [*texts, *_ACTION_LABELS.get(action, [])]
        else:
            texts = [action]
        for phrase in texts:
            if not isinstance(phrase, str) or not phrase.strip() or not _contains(text, phrase):
                continue
            head = _clauses(phrase)[0]
            local = [clause for clause in clauses if _contains(clause, head)]
            negated = False
            for clause in local:
                normalized, needle = _norm(clause), _norm(head)
                start = normalized.find(needle)
                prefix = normalized[max(0, start - 70):start].replace("do not hesitate to", "please").strip()
                if re.search(_NEGATIVE_PREFIX, prefix):
                    conflicts.append(clause)
                    negated = True
            if not negated and action in required:
                matched.extend(local or [text])
    if conflicts:
        return _check(True, 0.0, "contradiction", conflicts=list(dict.fromkeys(conflicts)), required_actions=required)
    if not required:
        return _check(False, None, "action_summary_optional_for_this_status", required_actions=[])
    if required[0] in unavailable:
        return _check(True, None, "action_catalog_unavailable", required_actions=required)
    return _check(True, 0.0 if conflicts else float(bool(matched)), "contradiction" if conflicts else "first_action_present" if matched else "missing_first_action",
                  matched=list(dict.fromkeys(matched)), conflicts=conflicts, required_actions=required)


def evaluate_response_consistency(prediction, *, valid, causes=None, questions=None, action_catalog=None, language="en"):
    """Equal mean of applicable dimension scores; unassessed dimensions count zero."""
    trace = {"method": "deterministic_english_rules", "version": RESPONSE_CONSISTENCY_VERSION,
             "uses_gold": False, "checks": {}, "assessment_coverage": 0.0, "unassessed_reason": None,
             "limitations": ["Finite English wording rules, not semantic equivalence or scientific correctness.",
                             "Unrecognized paraphrases can be reported as missing required wording.",
                             "ASK may omit actions; ANSWER requires only the first candidate and first action."]}
    if not valid or not isinstance(prediction, dict):
        trace["checks"] = {name: _check(True, None, "invalid_prediction") for name in _DIMENSIONS}
        return {"structured_output_vs_user_response_consistency": 0.0, "response_consistency": trace}
    status = prediction.get("status")
    actions = _ids(prediction.get("actions"))
    text = prediction.get("user_response", "")
    text = text if isinstance(text, str) else ""
    missing_response = not text.strip()
    if missing_response or (language is not None and (
        not isinstance(language, str) or language.casefold().split("-")[0].split("_")[0] != "en"
    )):
        reason = "missing_user_response" if missing_response else "unsupported_language"
        checks = {name: _check(True, None, reason) for name in _DIMENSIONS}
        if status != "needs_more_information":
            checks["questions"] = _check(False, None, "questions_optional_for_this_status")
        if missing_response and status != "provisional_assessment":
            checks["differential"] = _check(False, None, "candidate_summary_optional")
        if not actions or (missing_response and status != "provisional_assessment"):
            checks["actions"] = _check(False, None, "action_summary_optional_for_this_status", required_actions=[])
        trace["checks"] = checks
        trace["unassessed_reason"] = reason
        return {"structured_output_vs_user_response_consistency": None, "response_consistency": trace}
    clauses = _clauses(text)
    requests = [clause for clause in clauses if _request(clause)]
    certainty = [clause for clause in clauses if _certainty(clause)]
    current, conditional, rejected = _referrals(clauses)
    if status == "needs_more_information":
        status_score = float(bool(requests) and not certainty)
        status_reason = "contradiction" if certainty else "request_present" if requests else "missing_request"
    elif status == "provisional_assessment":
        status_score = float(bool(re.search(_PROVISIONAL, _norm(text))) and not certainty)
        status_reason = "contradiction" if certainty else "provisional_marker_present" if status_score else "missing_provisional_marker"
    elif status == "escalation_required":
        status_score = float(bool(current) and not rejected)
        status_reason = "contradiction" if rejected else "referral_present" if current else "missing_unconditional_referral"
    else:
        status_score, status_reason = 0.0, "unknown_status"
    trace["checks"]["status"] = _check(True, status_score, status_reason, matched=requests if status == "needs_more_information" else current if status == "escalation_required" else [clause for clause in clauses if re.search(_PROVISIONAL, _norm(clause))], conflicts=certainty if status != "escalation_required" else rejected)
    trace["checks"]["differential"] = _cause_check(text, clauses, _ids(prediction.get("differential")), causes, status)
    trace["checks"]["questions"] = _question_check(clauses, _ids(prediction.get("observations_needed")), questions, status)
    trace["checks"]["actions"] = _action_check(text, clauses, actions, action_catalog, status)
    if prediction.get("escalation_required") is True:
        esc_score = float(bool(current) and not rejected)
        esc_reason = "contradiction" if rejected else "referral_present" if current else "missing_unconditional_referral"
    else:
        mandatory = [clause for clause in current if re.search(r"\b(?:immediately|urgently|now|must|requires|need to|should)\b", _norm(clause))]
        esc_score = float(not mandatory)
        esc_reason = "contradiction" if mandatory else "no_conflicting_mandatory_referral"
        rejected = mandatory
    trace["checks"]["escalation"] = _check(True, esc_score, esc_reason, matched=current, conflicts=rejected, conditional_spans=conditional)
    applicable = [value for value in trace["checks"].values() if value["applicable"]]
    assessed = [value for value in applicable if value["score"] is not None]
    trace["assessment_coverage"] = len(assessed) / len(applicable) if applicable else 0.0
    score = sum(value["score"] or 0.0 for value in applicable) / len(applicable) if assessed else None
    if score is None:
        trace["unassessed_reason"] = "no_assessable_dimensions"
    return {"structured_output_vs_user_response_consistency": score, "response_consistency": trace}
