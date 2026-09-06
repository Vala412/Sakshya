"""Fixed retrieval queries and prompt templates for the explanation layer.

RETRIEVAL_QUERIES is deliberately a hand-written, reviewable constant, not
something derived from a finding's free-text evidence at call time. If the
query varied per finding, two occurrences of the same reason code could
retrieve different citations for reasons no one could audit later --
exactly the kind of nondeterminism this project's core engine was built to
avoid. Every reason code here should retrieve the same law, every time.

Only reason codes with real ITC impact (severity HIGH or MEDIUM in
exceptions.py) are listed. The LOW-severity codes (EX-02, EX-07, EX-08,
EX-12) are informational/timing observations with zero ITC at risk -- an
LLM call to explain "you have unclaimed credit available" would cost money
for no audit value, so explain.py never generates one.
"""

from __future__ import annotations

from gstrecon.exceptions import ReasonCode

RETRIEVAL_QUERIES: dict[ReasonCode, str] = {
    ReasonCode.EX_01: (
        "input tax credit available only if supplier has furnished invoice "
        "details in return communicated to recipient"
    ),
    ReasonCode.EX_03: "taxable value discrepancy tax invoice details furnished by supplier",
    ReasonCode.EX_04: "eligibility conditions for taking input tax credit tax invoice",
    ReasonCode.EX_05: "manner of utilisation of input tax credit integrated central state tax",
    ReasonCode.EX_06: (
        "input tax credit requires possession of tax invoice issued by "
        "supplier registered under this act"
    ),
    # Near-verbatim opening phrase of Section 17(5) itself, not a paraphrase
    # -- empirically verified (scripts/test_retrieval.py-style manual check)
    # that this ranks Section 17 (Apportionment of credit and blocked
    # credits) first at 0.635, versus a paraphrased query ("input tax
    # credit shall not be available blocked credits") that only ranked it
    # third at 0.550, behind two tangentially-related sections.
    ReasonCode.EX_09: (
        "notwithstanding anything contained input tax credit shall not be "
        "available in respect of the following"
    ),
    ReasonCode.EX_10: "input tax credit availed only once electronic credit ledger",
    ReasonCode.EX_11: (
        "credit note reduction in output tax liability corresponding "
        "reduction in input tax credit"
    ),
}

# Found by actually reading a real generated explanation, not assumed: an
# early version of this prompt produced "According to Section 17(1)..." for
# an excerpt labelled only "Section 17" -- the model invented a specific
# sub-section number that wasn't given to it (and picked the wrong one: the
# blocked-credits list the excerpt actually contains is sub-section (5),
# not (1)). The excerpt itself does contain sub-section numbers as part of
# its text, so the model isn't fabricating them from nothing -- but citing
# one as authoritative in a written explanation is exactly the kind of
# specific, falsifiable detail this project already treats as too risky to
# let an LLM state on its own (see explain.py's module docstring on never
# trusting the model to restate its own sources). The instruction below is
# a mitigation, not a guarantee -- there's no way to make an LLM incapable
# of this, only less likely to do it.
SYSTEM_PROMPT = """You are helping a chartered accountant understand a GST \
input tax credit reconciliation finding. You will be given the finding's \
details and one or more excerpts from the CGST Act or Rules.

Write a concise, plain-English explanation (2-4 sentences) of why this \
finding matters for input tax credit eligibility.

Refer to each excerpt only by the exact citation label given to you (e.g. \
"Section 17"). Do NOT cite a specific sub-section, clause, or explanation \
number (e.g. "Section 17(5)", "clause (a)") even if one appears inside the \
excerpt's text -- you cannot verify which sub-part is the one that applies \
here, and a wrong specific citation is worse than a general one. You may \
describe *what the excerpt says* in your own words without citing a
sub-part number.

Base your explanation ONLY on the provided excerpts -- not on general GST \
knowledge you may already have. Do not invent section numbers, rules, or \
legal claims that are not supported by the text given to you. If the \
excerpts do not clearly address this specific finding, say so explicitly \
rather than guessing or speculating."""


def build_user_message(
    *,
    reason_code: ReasonCode,
    description: str,
    evidence: str,
    itc_at_risk: str,
    excerpts: list[tuple[str, str]],
) -> str:
    """`excerpts` is a list of (citation_label, text) pairs, already
    retrieved and already past the similarity floor -- this function only
    formats what the caller decided is trustworthy enough to show the
    model, it doesn't make that decision itself.
    """
    excerpt_block = "\n\n".join(f"[{label}]\n{text}" for label, text in excerpts)
    return f"""Finding: {reason_code.value} -- {description}
Evidence: {evidence}
ITC at risk: Rs. {itc_at_risk}

Excerpts from the CGST Act/Rules:

{excerpt_block}"""
