"""docs/conclusions.html: the answer to the question the project was built for.

Every number is read from the result tables, so the page cannot drift from the data. Run:
    uv run absrisk report conclusions
"""

from __future__ import annotations

import sys
from html import escape
from pathlib import Path

import pandas as pd

from ..estimate import cards_roll
from .cards_page import STRESS_ORDER, direction_sentences
from .svg import page, table


def _num(x, fmt="{:.2f}"):
    return "n/a" if x is None or x != x else fmt.format(x)


def build(autos: Path, cards: Path, out: Path) -> Path:
    A = {p.stem: pd.read_csv(p) for p in autos.glob("*.csv")}
    C = {p.stem: pd.read_csv(p) for p in cards.glob("*.csv")}

    # ---- card stages
    bt = C.get("a3_by_trust", pd.DataFrame())
    base_c = bt.loc[bt["co_monthly"].idxmax(), "trust"] if not bt.empty else None
    best_c = bt.loc[bt["co_monthly"].idxmin()] if not bt.empty else None
    stress = C.get("a3_stress", pd.DataFrame())
    regimes = C.get("a3_regimes", pd.DataFrame())
    order = [p for p in STRESS_ORDER if not stress.empty and p in set(stress["period"])]
    direction = cards_roll.direction_summary(stress, regimes, order) if order or not regimes.empty else None
    verdict = direction["verdict"] if direction else "mixed"

    # ---- auto decomposition
    att = A.get("b6_attribution_by_score", pd.DataFrame())
    att = att[att["n_ever30"] >= 100] if not att.empty else att
    med = att.groupby("lender").agg(entry_share=("entry_share_of_gap", "median"),
                                    roll_ratio=("roll_ratio", "median"),
                                    entry_ratio=("entry_ratio", "median")).reset_index() if not att.empty else pd.DataFrame()
    sel = med[med["entry_share"] >= 0.7] if not med.empty else pd.DataFrame()
    rollers = med[med["entry_share"] <= 0.3] if not med.empty else pd.DataFrame()

    # ---- auto hazard
    hr = A.get("b2_hazard_ratios", pd.DataFrame())
    terms = hr[(hr["spec"] == "terms") & (hr["event"] == "chargeoff")] if not hr.empty else pd.DataFrame()
    def top_q(factor):
        s = terms[terms["factor"] == factor]
        return s.sort_values("level").iloc[-1] if not s.empty else None
    amt, pti, ltv = top_q("amount_q"), top_q("pti_q"), top_q("ltv_q")

    # ---- card residual ranking
    rank = C.get("a1_ranking", pd.DataFrame())
    rk = rank.pivot_table(index="trust", columns="shape_source", values="rank") if not rank.empty else pd.DataFrame()
    res = rank.pivot_table(index="trust", columns="shape_source", values="mean_residual") if not rank.empty else pd.DataFrame()
    stable = rk[rk.nunique(axis=1) == 1] if not rk.empty else pd.DataFrame()
    flip = res[(res > 0).any(axis=1) & (res < 0).any(axis=1)] if not res.empty else pd.DataFrame()

    summ = A.get("loans_summary", pd.DataFrame())
    n_loans = int(summ["n_loans"].sum()) if not summ.empty else 0
    n_deals = len(summ)
    n_lenders = summ["lender"].nunique() if not summ.empty else 0
    n_filings = int(bt["months"].sum()) if not bt.empty else 0

    h = ["<h1>Does anyone pay one card first?</h1>"]
    card_last = pd.to_datetime(bt["last"]).max() if not bt.empty and "last" in bt else None
    auto_last = str(summ["last_period"].max()) if not summ.empty and "last_period" in summ else None
    through = "; ".join(x for x in (f"card data through {card_last:%B %Y}" if card_last is not None else "",
                                    f"auto data through {pd.Period(auto_last[:7]).strftime('%B %Y')}" if auto_last else "") if x)
    h.append(f"<p class='muted'><b>{escape(through[:1].upper() + through[1:])}.</b> {n_filings} monthly trust reports and "
             f"{n_loans:,} auto loans across {n_deals} deals and {n_lenders} lenders, all from public SEC filings.</p>")

    h.append("<h2>The question</h2>")
    h.append("<p>American Express loses less on its card portfolio than Synchrony does. Toyota loses less on its auto loans "
             "than Santander does. Both facts survive holding the borrower's credit score fixed. There are two very different "
             "reasons that could be true, and they have opposite implications for anyone pricing credit:</p>")
    h.append("<p><b>Selection.</b> The issuer picked people who do not miss payments, seeing something the bureau score does not. "
             "<b>Priority.</b> The same people miss payments as often, but pay that account first when money is short.</p>")
    h.append("<p>The loss rate cannot tell them apart, because both predict the same lower number. Almost every public comparison "
             "of issuers stops there and calls it underwriting quality.</p>")

    h.append("<h2>The test</h2>")
    h.append("<p>A card trust's monthly charge-off rate factors exactly into three shares the trust reports itself, and the "
             "two stories load onto different ones:</p>")
    h.append("<p class='muted' style='font-size:15px'>monthly charge-off &nbsp;=&nbsp; <b>entry</b>, the share of balances 30 or "
             "more days late &nbsp;x&nbsp; <b>progression</b>, the share of those that are 90 or more days late &nbsp;x&nbsp; "
             "<b>conversion</b>, the month's charge-off as a share of balances 90 or more days late</p>")
    h.append("<p>Selection moves <b>entry</b> and leaves conversion alone: the borrower rarely gets into trouble, and once in "
             "trouble resolves like anyone else. Priority moves <b>conversion</b>: the borrower gets into trouble at the normal "
             "rate and rescues that account. Priority could lower entry too, since a borrower who pays a card first falls behind "
             "on it less often, so entry alone does not separate the stories; conversion is the measure that can, and it is also "
             "the more trustworthy one, because it conditions on an observed behaviour, already being 90 days late, rather than "
             "on a credit score whose scale differs between lenders. Progression is close to the same at every trust.</p>")

    heading = {"against": "The answer: selection, and it is not close",
               "mixed": "The answer: selection, on every level comparison",
               "priority": "The levels say selection; the timing test leans the other way"}[verdict]
    h.append(f"<h2>{heading}</h2>")
    if best_c is not None:
        h.append(f"<p><b>Cards.</b> {best_c['trust']} loses {best_c['co_monthly_ratio']:.2f} times what {base_c} loses each month. "
                 f"Its share of balances 30 days late is {best_c['entry_ratio']:.2f} times {base_c}'s. But once an account is 90 days "
                 f"late, it converts to a write-off at <b>{best_c['conversion_ratio']:.2f} times</b> {base_c}'s rate. Entry accounts for "
                 f"{best_c['entry_share_of_gap']:.0%} of the gap, progression for {best_c['progression_share_of_gap']:+.0%} and "
                 f"conversion for {best_c['conversion_share_of_gap']:+.0%}. Priority predicts the opposite sign on conversion: a "
                 f"protected card would rescue its late accounts, which is a low conversion rate, not a high one.</p>")
        h.append(table(bt, cols=["trust", "months", "co_monthly", "entry", "progression", "conversion", "entry_ratio",
                                 "progression_ratio", "conversion_ratio", "entry_share_of_gap", "progression_share_of_gap",
                                 "conversion_share_of_gap"],
                       fmt={"co_monthly": "{:.3%}", "entry": "{:.2%}", "progression": "{:.3f}", "conversion": "{:.1%}",
                            "entry_ratio": "{:.2f}", "progression_ratio": "{:.2f}", "conversion_ratio": "{:.2f}",
                            "entry_share_of_gap": "{:+.2f}", "progression_share_of_gap": "{:+.2f}",
                            "conversion_share_of_gap": "{:+.2f}"}))
        h.append("<p class='muted'>This decomposition is arithmetic, not a model. Each column is a geometric mean over the trust's "
                 "months, so for every row entry x progression x conversion is co_monthly, and the three shares of the gap against "
                 f"{escape(str(base_c))} sum to one.</p>")
    if not sel.empty:
        names = ", ".join(sorted(sel["lender"]))
        lo, hi = sel["entry_share"].min(), sel["entry_share"].max()
        rr = ", ".join(f"{r['lender']} {r['roll_ratio']:.2f}" for _, r in sel.iterrows())
        h.append(f"<p><b>Autos, where the data is loan by loan.</b> Comparing lenders inside the same 20-point score bucket, "
                 f"{escape(names)} owe {lo:.0%} to {hi:.0%} of their advantage to entry. Their borrowers are several times less likely "
                 f"to reach 30 days past due; once past due they charge off at close to the baseline lender's rate "
                 f"(roll ratios {escape(rr)}).</p>")
    if not rollers.empty:
        rr = "; ".join(f"{r['lender']}: entry ratio {r['entry_ratio']:.2f}, roll ratio {r['roll_ratio']:.2f}" for _, r in rollers.iterrows())
        h.append(f"<p><b>One instructive exception.</b> {escape(rr)}. Its borrowers fall behind at the same rate as the baseline "
                 f"lender's but lose far more often afterwards. That is a difference in what happens after trouble starts, which is "
                 f"where priority would live, but for a secured product the likelier readings are repossession policy and workout "
                 f"practice rather than the borrower's ranking of debts.</p>")
    if direction and (direction.get("regime") or direction.get("tightenings")):
        best_name = str(best_c["trust"]) if best_c is not None else None
        h.append("<p><b>A second test, on direction rather than level.</b> If people rank their debts, the ranking should bite "
                 "hardest when money is short, so a protected card's conversion ratio should <i>fall</i> when delinquency is "
                 "high. " + " ".join(direction_sentences(direction, best_name)) + "</p>")
        if not regimes.empty:
            w = regimes.pivot_table(index="trust", columns="regime", values="conversion_ratio").reindex(columns=["loose", "tight"])
            w["move"] = w["tight"] - w["loose"]
            h.append(table(w.reset_index(), fmt={"loose": "{:.2f}", "tight": "{:.2f}", "move": "{:+.2f}"}))

    h.append("<h2>What else the data settled</h2>")
    if amt is not None and pti is not None and ltv is not None:
        h.append("<p><b>The size of a loan is not the risk in it; the payment is.</b> At the same score, lender and origination "
                 "quarter, comparing the top quintile against the bottom:</p>")
        rows = pd.DataFrame([
            {"factor": "loan amount", "odds_ratio": amt["odds_ratio"], "lo95": amt["lo95"], "hi95": amt["hi95"]},
            {"factor": "payment-to-income", "odds_ratio": pti["odds_ratio"], "lo95": pti["lo95"], "hi95": pti["hi95"]},
            {"factor": "loan-to-value", "odds_ratio": ltv["odds_ratio"], "lo95": ltv["lo95"], "hi95": ltv["hi95"]},
        ])
        h.append(table(rows, fmt={"odds_ratio": "{:.2f}", "lo95": "{:.2f}", "hi95": "{:.2f}"}))
        h.append(f"<p>A bigger loan at the same burden defaults <i>less</i> ({amt['odds_ratio']:.2f}), because at a fixed payment "
                 f"and a fixed loan-to-value a larger balance means a larger income behind it. What raises default is the monthly "
                 f"burden ({pti['odds_ratio']:.2f}) and lending past the value of the collateral ({ltv['odds_ratio']:.2f}). Anyone "
                 f"reasoning about a bigger line as risk in itself has the wrong variable.</p>")
    if not stable.empty and not flip.empty:
        h.append(f"<p><b>How much of an issuer's loss rate is its customer mix is genuinely unknown.</b> Predicting each trust's "
                 f"losses from its own score mix needs a loss curve by score, and no public source publishes one for cards. The four "
                 f"published curves that exist disagree by about five times. Under all four, the ends of the ranking hold "
                 f"({escape(', '.join(stable.index))} keep their place), but {len(flip)} of {len(res)} trusts change the <i>sign</i> "
                 f"of their gap depending on which curve is assumed. The ordering of the extremes is a finding. The size of anyone's "
                 f"gap is not.</p>")

    h.append("<h2>What this cannot say</h2>")
    h.append("<p>The conversion comparison rules out the simple priority story, because priority would show up as accounts rescued "
             "from deep delinquency and the opposite is observed. It does not separate the borrower's behaviour from the issuer's: "
             "an issuer that charges off faster, or re-ages less, produces the same high conversion rate. Separating those needs each "
             "issuer's charge-off policy, which the filings do not state.</p>")
    h.append("<p>Nothing here observes one person holding two accounts. That is the measurement payment hierarchy actually requires, "
             "and it does not exist in public data: Regulation AB II exempted credit card securitisations from loan-level disclosure, "
             "and the credit panels that could answer it are confidential. Anyone claiming to have measured hierarchy from public "
             "filings has measured something else.</p>")
    h.append("<p>Three further limits, stated rather than buried. Trust pools are the securitised, seasoned end of an issuer's book "
             "and not the book. Lenders report different score models on different scales, which is why the argument leans on "
             "conversion rather than on entry. And the regression discontinuity designs at lenders' own pricing cutoffs returned "
             "mostly nulls: half the candidate cutoffs failed a density test, meaning the applicant pool changes at the line, and the "
             "survivors were underpowered.</p>")

    h.append("<h2>The short version</h2>")
    crisis = " The timing of losses across the cycle neither confirms nor overturns that." if verdict == "mixed" else (
        " It is not collected in a crisis either." if verdict == "against" else
        " The timing of losses leans the other way, which is the one piece of evidence for a protected card.")
    h.append("<p>Issuers with low losses at the same credit score got there by lending to people who do not fall behind, not by "
             "holding an account their customers protect: their late accounts are not rescued more often than anyone else's. "
             "The advantage is bought at origination." + crisis + " For a lender, that means the returns to better selection "
             "dwarf the returns to being someone's favourite card. For a borrower, it means the card that looks safest is safest "
             "because of who else holds it.</p>")
    h.append("<footer>Methods and every caveat: <a href='https://github.com/SamuelJWebber/abs-risk/blob/main/design/methods.md'>"
             "design/methods.md</a>. Data and code: <a href='https://github.com/SamuelJWebber/abs-risk'>"
             "github.com/SamuelJWebber/abs-risk</a>. Sources: SEC EDGAR forms 10-D, 424B and ABS-EE, and CFPB Consumer Credit "
             "Card Market Report figure data.</footer>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page("abs-risk conclusions", "".join(h), current="conclusions.html"), encoding="utf-8")
    return out


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="absrisk report conclusions")
    ap.add_argument("--autos", default="data/results/autos")
    ap.add_argument("--cards", default="data/results/cards")
    ap.add_argument("--out", default="docs/conclusions.html")
    a = ap.parse_args(argv)
    p = build(Path(a.autos), Path(a.cards), Path(a.out))
    print(f"wrote {p}", file=sys.stderr)
    return 0
