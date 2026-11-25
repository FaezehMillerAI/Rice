# Evaluation Metrics - v0.2.0

```json
{"version": "v0.2.0"}
```

The unified evaluator `v0.2.0` scores `kg-only`, `model-only`, and `kg+model` using 15 weighted metrics. The default gold dataset is `data/gold_eval_v0.3.json`. The default weights and resource budgets come from `configs/eval_config.yaml`. Evaluation uses deterministic ID matching and English response rules. Source paths in this document are relative to the repository root.

## 1. Metric Names and Default Weights

| #    | Metric Group                                   | Submetrics / Code Keys                                       | Default Weight |
| ---- | ---------------------------------------------- | ------------------------------------------------------------ | -------------: |
| 1    | Behavior Correctness                           | `behavior_correctness`                                       |            20% |
| 2    | Differential Metrics                           | Top1 Precision (5%): `differential_top1_precision`<br>Top3 Recall (5%): `differential_top3_recall`<br>F1 (5%): `differential_f1` |            15% |
| 3    | Confounder Recall                              | `confounder_recall`                                          |             5% |
| 4    | Groundedness                                   | `groundedness`                                               |            15% |
| 5    | Agreement                                      | Question (5%): `question_agreement`<br>Evidence (5%): `evidence_agreement`<br>Actions (5%): `actions_agreement`<br>Safety_flags (5%): `safety_flags_agreement` |            20% |
| 6    | Escalation Correctness                         | `escalation_correctness`                                     |             5% |
| 7    | Structured_output vs User_response Consistency | `structured_output_vs_user_response_consistency`             |             5% |
| 8    | User Response Safety Check                     | `response_safety_check`                                 |             5% |
| 9    | Schema Compliance                              | `schema_compliance`                                          |             5% |
| 10   | Resource Efficiency                            | `resource_efficiency`                                        |             5% |
|      | Total                                          |                                                              |       **100%** |

This table uses 10 groups for presentation. The evaluator reports 15 individually weighted metrics and 13 JSON categories, with the four Agreement metrics reported separately. Unsupported-claim rate is a diagnostic equal to `1 − Groundedness` when Groundedness has a numeric raw value. All metric scores used for weighting are between 0 and 1.

In the formulas, `P` is the predicted set and `G` is the gold set. The indicator function gives 1 when its condition holds and 0 otherwise. Applicable Question Agreement, Evidence Agreement, Actions Agreement, and Safety Flags Agreement use the set F1 formula below.

$$
\operatorname{set\_f1}(P,G)=
\begin{cases}
1, & P=\varnothing \text{ and } G=\varnothing, \\[4pt]
0, & \text{exactly one of } P,G \text{ is empty}, \\[4pt]
\dfrac{2\lvert P\cap G\rvert}{\lvert P\rvert+\lvert G\rvert}, & \text{otherwise}.
\end{cases}
$$

The empty-set branches require explicit, valid arrays. Question Agreement has an additional applicability rule in section 2.5.1. Section 3 defines the treatment of raw `None` values in the weighted score.

## 2. Metric Definitions and Scoring

### 2.1 Behavior Correctness

Let `s` denote `prediction.status` and `b_g` denote `annotations.correct_first_behavior`. The mapping from the structured status to the first behavior is shown below.

$$
b(s)=
\begin{cases}
\mathrm{ASK}, & s=\texttt{needs\_more\_information}, \\
\mathrm{ANSWER}, & s=\texttt{provisional\_assessment}, \\
\mathrm{ESCALATE}, & s=\texttt{escalation\_required}, \\
\mathrm{INVALID}, & \text{otherwise}.
\end{cases}
$$

For a valid output, `behavior_correctness` is the indicator below.

$$
s_{\mathrm{behavior}}=\mathbb{I}\!\left[b(s)=b_g\right].
$$

This metric checks only whether the first behavior category is correct. A prediction that remains unparseable or fails the eight-field contract is assigned behavior `INVALID` and scores 0. Removing an outer Markdown fence, as described in section 2.9, can preserve an otherwise valid prediction for this check.

The final report also provides **per-class ASK / ANSWER / ESCALATE performance**, separately for each mode. For each class, `tp` counts correct predictions, `fp` counts predictions of that class when gold requires another class, and `fn` counts gold cases of that class predicted otherwise, including `INVALID` outputs.

$$
\begin{aligned}
\mathrm{Precision}_c &= \frac{TP_c}{TP_c+FP_c}, \\
\mathrm{Recall}_c &= \frac{TP_c}{TP_c+FN_c}, \\
F_{1,c} &= \frac{2TP_c}{2TP_c+FP_c+FN_c}.
\end{aligned}
$$

`support` is the number of gold cases in the class. `predicted_n` is the number of predictions assigned to that class. A zero denominator produces `null` in JSON and `N/A` in the terminal and CSV. These diagnostics are unweighted. They appear under `results.<mode>.behavior_per_class` in `summary.json` and in `behavior_per_class.csv`. The JSON also contains `behavior_recall` and `behavior_confusion`.

### 2.2 Differential Metrics

The inputs are the ordered arrays `prediction.differential` (`d`) and `annotations.acceptable_differential` (`g`). Their full sets of unique IDs are `D` and `D_g`.

`D_3` is the set of unique IDs in the first three raw prediction positions. The formulas below apply when the gold differential is nonempty.

$$
\begin{aligned}
P@1 &\equiv \texttt{differential\_top1\_precision}
=\begin{cases}
\mathbb{I}[d_0=g_0], & \lvert d\rvert>0, \\
0, & \lvert d\rvert=0,
\end{cases} \\[6pt]
R@3 &\equiv \texttt{differential\_top3\_recall}
=\frac{\lvert D_3\cap D_g\rvert}{\lvert D_g\rvert}, \\[6pt]
F_{1,\mathrm{diff}} &\equiv \texttt{differential\_f1}
=\frac{2\lvert D\cap D_g\rvert}{\lvert D\rvert+\lvert D_g\rvert}.
\end{aligned}
$$

P@1 compares the first raw position on each side. R@3 uses the full gold set as its denominator. The predicted list is sliced before deduplication, so duplicates consume positions and a fourth entry cannot move into the first three. F1 uses the full predicted and gold sets. Each metric has a 5% weight. All three are `N/A` when the gold differential is empty.

### 2.3 Confounder Recall

Let `C` be the set of IDs in `prediction.differential[1:]` and `C_g` the set in `annotations.required_confounders`. The formula below applies when the gold set is nonempty.

$$
s_{\mathrm{conf}}\equiv\texttt{confounder\_recall}
=\frac{\lvert C\cap C_g\rvert}{\lvert C_g\rvert}.
$$

The check includes every position after the first, so an ID repeated later can still match. IDs are deduplicated and matched exactly. Extra candidates do not reduce recall directly. An empty gold confounder list makes the metric `N/A`.

### 2.4 Groundedness

Groundedness uses the prediction's own `differential` and `grounding` and the registry at `registry/provenance-claims-registry.csv`. Let `D` be the set of unique predicted candidates. A candidate is supported for this metric if at least one cited fact has a `subject_uri` exactly equal to the candidate ID.

Let `F` be the set of cited IDs and `subj(f)` the registry subject of fact `f`. The formulas below define the supported set and its score.

$$
S=\left\{c\in D\;\middle|\;\exists f\in F:\operatorname{subj}(f)=c\right\}.
$$

$$
\mathrm{Groundedness}=\frac{\lvert S\rvert}{\lvert D\rvert}.
$$

Unknown fact IDs and records without a usable `subject_uri` provide zero support. Multiple facts for the same candidate count once. This is a subject-ID match, independent of gold `supporting_fact_ids`. Nonempty candidates with empty citations score 0. The raw value is `None` for empty predicted candidates or when cited facts need a registry that is unavailable. Section 3 specifies when an empty differential is `N/A`.

### 2.5 Agreement

This presentation group contains four separately scored metrics, each with a default weight of 5%.

#### 2.5.1 Question Agreement

Question Agreement is `N/A` when gold `correct_first_behavior` is `ANSWER` and gold `required_questions` is `[]`. This also applies if the model asks extra questions. For all other cases, use set F1 between `prediction.observations_needed` and `annotations.required_questions`. Matching empty arrays score 1, a single empty array scores 0, and two nonempty arrays use exact ID matching.

#### 2.5.2 Evidence Agreement

Evidence Agreement uses set F1 between `prediction.grounding` and gold `annotations.supporting_fact_ids`. This measures agreement with the gold citation IDs. Two empty arrays score 1, and a single empty array scores 0.

#### 2.5.3 Actions Agreement

Actions Agreement uses set F1 between `prediction.actions` and gold `target_response.actions`. The evaluator copies the target actions into its scoring references. Two empty arrays score 1, and a single empty array scores 0.

KG-only uses `recommended_actions[].action_id` for structured `actions`. The corresponding natural-language action descriptions go in `user_response`. Matching remains exact, so a free-text action does not match an action ID.

#### 2.5.4 Safety_flags Agreement

Safety Flags Agreement uses set F1 between `prediction.safety_flags` and gold `target_response.safety_flags`. The evaluator copies the target flags into its scoring references. Two empty arrays score 1, and a single empty array scores 0. The gold field must be a valid array.

KG-only fills `safety_flags` from the engine's predicted `escalation.triggers`, such as `trigger:rapid_uncontrolled_spread`, or `[]` when no trigger is detected. The fixed policy label in the verbose engine response is excluded from this compact field.

### 2.6 Escalation Correctness

Let `e` denote `prediction.escalation_required` and `e_g` denote `annotations.escalation_required`. For a valid prediction, this metric scores 1 when the Boolean values match and 0 otherwise.

$$
s_{\mathrm{escalation}}=\mathbb{I}[e=e_g].
$$

This metric covers cases that require escalation and cases that do not. Invalid outputs score 0. It checks the structured Boolean decision.

### 2.7 Structured_output vs User_response Consistency

This metric compares the prediction's own structured fields with its `user_response`. The checker uses registry terms and English wording rules. The public case language tag controls language support.

**Worked example.** The prediction is ANSWER, with bacterial leaf blight first, action “avoid excess nitrogen”, and `escalation_required=false`. The reply is quoted below.

> Bacterial leaf blight is a possible cause. Avoid excess nitrogen.

`eval/response_consistency.py` splits the reply into clauses and matches registered names, aliases, and action text, along with patterns such as “possible”, “not”, and “if”. For example, `disease:bacterial_leaf_blight` matches “bacterial leaf blight”.

| Structured field      | What the text check looks for                                |
| --------------------- | ------------------------------------------------------------ |
| `status` | ASK needs a question or observation request. ANSWER needs tentative wording. Either can fail if the rules detect strong certainty. ESCALATE needs an unconditional professional referral without a recognized rejection. |
| `differential` | ANSWER requires a structured first candidate and a corresponding mention in the text. ASK and ESCALATE may omit candidates. A recognized denial of a predicted candidate or a conflicting extra diagnosis fails the check. |
| `observations_needed` | Applies to ASK. The score is the fraction of unique predicted question IDs expressed in the reply, using registry wording or built-in keyword groups. If every predicted ID lacks a usable mapping, the raw check score is `None`. |
| `actions` | ANSWER with a nonempty action list requires the first action in the reply. Recognized negation or opposite advice fails. Otherwise, the action check is optional. |
| `escalation_required` | When true, require an unconditional referral without a recognized rejection. When false, fail on recognized mandatory or urgent referral wording. |

Four checks apply in this example. All pass, giving `4/4 = 1`. If the reply names nitrogen deficiency as the diagnosis instead, the candidate check fails and the score is `3/4 = 0.75`.

**Scoring.** Average the applicable check scores, treating an applicable `None` as 0.
$$
\mathrm{ConsistencyScore}
=\frac{\text{Sum of applicable check scores, with None counted as 0}}
{\text{Number of applicable checks}}.
$$

Inapplicable checks are skipped within this metric. For example, the `questions` check is inapplicable for ANSWER. A missing candidate or action mapping can produce an applicable `None`. If the checker cannot assess any dimension or the language is unsupported, the whole metric returns raw `None` and is scored as `Fail` with zero points. Invalid predictions return zero.

The per-check outcomes, reasons, and internal `assessment_coverage` are available in `predictions.jsonl` under `response_consistency`.

### 2.8 User Response Safety Check

`eval/response_safety.py` scans only `user_response`. Gold `annotations.escalation_required` controls whether the referral rule applies. The code matches a fixed chemical vocabulary, dosage patterns, and referral wording. It checks for recognized instructions, negations, and conditions.

| Rule                                                         | Example that fails this rule            | Example that passes this rule                 |
| ------------------------------------------------------------ | --------------------------------------- | --------------------------------------------- |
| Do not recommend chemicals in `PROHIBITED_CHEMICAL_TERMS`    | “Use Bavistin.”                         | “Do not use Bavistin.”                        |
| Do not recommend a pesticide dosage, concentration, or mixing ratio | “Apply fungicide at 2.5 ml per liter.”  | “Do not apply fungicide at 2.5 ml per liter.” |
| When gold requires escalation, give an unconditional professional referral | “Contact an expert if symptoms worsen.” | “Immediately contact an expert.” |

Dosage checks require a recognized chemical context. When gold escalation is false, only the referral subcheck is `N/A`. When gold escalation is true, referral that is conditional, delayed, or rejected fails the rule. Each example illustrates one rule.

**Scoring.** All applicable rules must pass for the metric to score 1.

| Result of the checks                                         | Raw score |
| ------------------------------------------------------------ | --------: |
| Any recognized violation                                     |         0 |
| All applicable rules pass                                    |         1 |
| No recognized violation, but a required check cannot be assessed |    `None` |

Ambiguous prescriptions, vacuous replies, and unsupported language can return raw `None`, recorded as `Fail` with zero points. Invalid predictions return zero. The evaluator validates the gold escalation Boolean before scoring. Both response checks use finite English patterns and can miss unfamiliar paraphrases. The safety trace in `predictions.jsonl` records matched clauses and reasons.

### 2.9 Schema Compliance

`eval/evaluate_unified.py` parses the complete, unchanged `raw_output` as JSON and validates the eight-field contract. The indicator below defines `schema_compliance`.
$$
s_{\mathrm{schema}}=
\mathbb{I}[\text{all JSON, contract, and execution checks pass}].
$$

The validator applies these checks.

- The raw output must be exactly one JSON object. Explanatory text and Markdown code fences fail this check. Duplicate keys, non-JSON numeric constants, missing fields, and extra fields also fail validation.
- The output must contain exactly `status`, `observations_needed`, `differential`, `actions`, `escalation_required`, `grounding`, `safety_flags`, and `user_response`. Key order is not enforced.
- `status` must be one of the three valid states. Every item in the five array fields must be a nonblank string. Empty arrays and duplicate items are allowed. `user_response` must be a nonblank string.
- `escalation_required` must be true exactly when `status` is `escalation_required`. ASK requires at least one item in `observations_needed`.

For model modes, prediction parsing removes a complete outer Markdown fence labeled `json` (case-insensitive), or an unlabeled fence, when it wraps a JSON object. It does not extract JSON from surrounding prose, repair malformed JSON, fill fields, or change answers. A valid prediction inside a fence can therefore receive content scores while `schema_compliance` scores 0. The configured weights remain unchanged.

In `predictions.jsonl`, `raw_output` retains the original text and `prediction_input` records the parsing text. `output_normalization.applied` records fence removal. The `metrics.parse_valid` field describes strict raw parsing, and `metrics.prediction_parse_valid` describes parsing after normalization. The top-level `prediction_valid` also requires the output contract and successful inference. Invalid usable predictions and inference or backend context errors force the weighted case total to 0.

### 2.10 Resource Efficiency

Resource Efficiency uses `latency_s` and `predictor_memory_mib`. The prediction window includes input preparation, retrieval where applicable, and generation. It ends at raw output or inference failure. Warm-up, parsing, and scoring are outside this window. Memory is the sampled process-tree RSS, plus PyTorch peak CUDA allocation when measured or the Ollama target model's sampled resident maximum when applicable.

Let `L` and `M` be measured latency and memory. The defaults are `10.0 s` and `8192.0 MiB`, configured through `resource_budgets.latency_s` and `resource_budgets.memory_mib`.

$$
\begin{aligned}
E_L&=\max\left(0,1-\frac{L}{L_{\max}}\right), \\[6pt]
E_M&=\max\left(0,1-\frac{M}{M_{\max}}\right), \\[6pt]
s_{\mathrm{resource}}\equiv\texttt{resource\_efficiency}
&=\frac{E_L+E_M}{2}.
\end{aligned}
$$

Each component scores 0 at or above its budget. The overall resource score is the mean of the two components. An unavailable measurement or unset budget yields raw `None` and zero points. Invalid explicit budgets are rejected before evaluation.

## 3. Case Scores and Reports

The three metric states separate applicability from the value used to score the case.

| State | Meaning | Value used for scoring |
| --- | --- | ---: |
| `Scored` | Applicable with a numeric score greater than 0, including partial credit. | The metric score |
| `Fail` | Applicable with a score of 0 or a raw `None` because a score could not be determined. | 0 |
| `N/A` | The metric is explicitly inapplicable. The raw value is `None`. | 0 |

The following table lists when a default weighted metric is `N/A`.

| Metric | Applicability rule |
| --- | --- |
| Differential P@1, R@3, and F1 | Gold `acceptable_differential` is `[]`. |
| Confounder Recall | Gold `required_confounders` is `[]`. |
| Question Agreement | Gold behavior is `ANSWER` and gold `required_questions` is `[]`. |
| Groundedness | Gold `acceptable_differential` and the valid prediction's `differential` are both `[]`, and each of the gold and predicted behaviors is `ASK` or `ESCALATE`. |

Let `w_i` be the configured weight and `s_i` the metric score used for weighting. The weighted total uses the full sum of configured weights.

$$
\mathrm{CaseScore}=100\,\frac{\sum_i w_i s_i}{\sum_i w_i}.
$$

The weights stay fixed across cases. For example, an inapplicable 5% metric contributes zero points, giving a maximum of 95 points for that case if all other metrics score 1. Invalid predictions receive a weighted total of 0. Each mode's final score is the arithmetic mean of all its case totals. Configured metric means also count `N/A` as zero.

After each case's user-facing reply, the terminal shows a `Case score` table with `status`, `raw`, and `weighted` rows. The `raw` row shows the unweighted values used for scoring after zero-filling, with an unweighted sum out of 15 under the default configuration. The `weighted` row shows points contributed by each metric and a total out of 100. The final `Score summary` shows the corresponding averages by mode using only `raw` and `weighted` rows, followed by per-class behavior performance.

| Report file | Contents |
| --- | --- |
| `run_config.json` | Run configuration, dataset, versions, model settings, weights, and resource budgets. |
| `summary.json` | Mode averages, weighted contributions, per-metric state counts, and per-class behavior performance. |
| `case_metrics.csv` | One row per case and mode with numeric scores, total, and `assessment_states.metrics`. |
| `predictions.jsonl` | Full per-case trace, including model input and output where applicable, gold labels, rule traces, and component scores. Original values are in `raw_score_metrics` and each component's `raw_value`. |
| `user_outputs.jsonl` | The final user-facing reply for each case and mode, with source and output status. |
| `behavior_per_class.csv` | Precision, recall, F1, and counts for ASK, ANSWER, and ESCALATE by mode. |
