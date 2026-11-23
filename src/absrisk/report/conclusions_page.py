"""docs/conclusions.html: what the filings can and cannot say about the question the project was built for.

Every number is read from the result tables, so the page cannot drift from the data. Run:
    uv run absrisk report conclusions

Until 2026-11-21 this page concluded "selection, on every level comparison" from the card conversion ratio. The
independent review of 2026-11-10 (REVIEW.md abs-A-2, abs-B-2) showed that ratio is not the fate of late accounts, so
the page now says what entry shows and that the filings are silent on rescue. tests/test_conclusions_claims.py holds
the withdrawn sentences off the page.
"""

from __future__ import annotations

import sys
from html import escape
from pathlib import Path

import pandas as pd

from ..estimate import cards_roll
from .cards_page import STRESS_ORDER, _gross_residuals, direction_sentences, ends, ends_clause
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
    straddle = C.get("a1_straddle", pd.DataFrame())
    e = ends(straddle if not straddle.empty else rank) if not rank.empty else None
    if not rank.empty:
        glo, ghi = _gross_residuals(rank)       # like for like with the CFPB's gross level (cards page, section 4)
        keeps = ((glo > 0).all(axis=1) & (ghi > 0).all(axis=1)) | ((glo < 0).all(axis=1) & (ghi < 0).all(axis=1))
        flip = glo[~keeps]
    else:
        flip = pd.DataFrame()
    ceil = C.get("a3_ceiling", pd.DataFrame())

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
    h.append("<p>The American Express card trust loses less than Synchrony's. Toyota's public auto loan pool loses less than "
             "Santander's, and that one holds with the borrower's credit score fixed; for the card trusts, whether it does "
             "depends on which loss curve is assumed. These are one securitised trust per card issuer and one or two public "
             "deals per auto lender, not the lenders' whole books. There are two very different reasons a lender's losses "
             "could be lower, and they have opposite implications for anyone pricing credit:</p>")
    h.append("<p><b>Selection.</b> The issuer picked people who do not miss payments, seeing something the bureau score does not. "
             "<b>Priority.</b> The same people miss payments as often, but pay that account first when money is short.</p>")
    h.append("<p>The loss rate cannot tell them apart, because both predict the same lower number. Almost every public comparison "
             "of issuers stops there and calls it underwriting quality.</p>")

    h.append("<h2>What can be measured</h2>")
    h.append("<p>A card trust's monthly charge-off rate factors exactly into three shares the trust reports itself:</p>")
    h.append("<p class='muted' style='font-size:15px'>monthly charge-off &nbsp;=&nbsp; <b>entry</b>, the share of balances 30 or "
             "more days late &nbsp;x&nbsp; <b>progression</b>, the share of those that are 90 or more days late &nbsp;x&nbsp; "
             "<b>conversion</b>, the month's charge-off as a share of balances 90 or more days late</p>")
    h.append("<p><b>Entry</b> is where both stories speak, and they say the same thing: an issuer that selected well has few "
             "accounts falling behind, and so does an issuer whose card is paid first. The stories part only on what happens "
             "to an account once it is late. <b>Conversion</b> looks like that measure and is not one: its numerator is every "
             "charge-off in the month, including accounts written off on bankruptcy or death that were never 90 days late. "
             "Progression is close to the same at every trust.</p>")

    h.append("<h2>What the filings show: far fewer late balances, and nothing on rescue</h2>")
    mix = C.get("mix_by_trust", pd.DataFrame())
    product = C.get("a1_product", pd.DataFrame())
    if best_c is not None:
        base_pl = ""
        if not mix.empty and "private_label_share" in mix:
            mb = mix[mix["trust"] == base_c]
            if not mb.empty and float(mb["private_label_share"].iloc[-1]) > 0:
                w = float(mb["private_label_share"].iloc[-1])
                base_pl = f" ({escape(str(base_c))} is a retail pool, {w:.1%} private-label receivables in its latest prospectus, with the rest dual cards and Mastercard)"
        h.append(f"<p><b>Cards.</b> {best_c['trust']} loses {best_c['co_monthly_ratio']:.2f} times what {base_c} loses each month, "
                 f"after recoveries{base_pl}. Its share of balances 30 days late is {best_c['entry_ratio']:.2f} times {base_c}'s. Entry "
                 f"accounts for {best_c['entry_share_of_gap']:.0%} of the gap, progression for "
                 f"{best_c['progression_share_of_gap']:+.0%} and conversion for {best_c['conversion_share_of_gap']:+.0%}. "
                 f"So the gap in losses is a gap in how many balances are late at all. Selection predicts that, and so does a "
                 f"card that is paid first.</p>")
        h.append(table(bt, cols=["trust", "months", "co_monthly", "entry", "progression", "conversion", "entry_ratio",
                                 "progression_ratio", "conversion_ratio", "entry_share_of_gap", "progression_share_of_gap",
                                 "conversion_share_of_gap"],
                       fmt={"co_monthly": "{:.3%}", "entry": "{:.2%}", "progression": "{:.3f}", "conversion": "{:.1%}",
                            "entry_ratio": "{:.2f}", "progression_ratio": "{:.2f}", "conversion_ratio": "{:.2f}",
                            "entry_share_of_gap": "{:+.2f}", "progression_share_of_gap": "{:+.2f}",
                            "conversion_share_of_gap": "{:+.2f}"}))
        h.append("<p class='muted'>This decomposition is arithmetic, not a model. Each column is a geometric mean over the trust's "
                 "months, on the net charge-off rate every trust prints, so for every row entry x progression x conversion is "
                 f"co_monthly, and the three shares of the gap against {escape(str(base_c))} sum to one.</p>")
    if not ceil.empty:
        c = ceil.set_index("trust")
        one = c[c["bucket_months"] == 1].sort_values("chargeoff_over_one_month", ascending=False)
        two = c[c["bucket_months"] > 1]
        bits = []
        if not one.empty and one.iloc[0]["chargeoff_over_one_month"] > 1:
            t, r = one.index[0], one.iloc[0]
            bits.append(f"{escape(str(t))} wrote off {r['chargeoff_over_one_month']:.2f} times the dollars in that bucket, so "
                        f"at least {r['min_share_not_aged']:.0%} of its charge-offs never aged through late delinquency")
        for t, r in two.iterrows():
            if r["chargeoff_over_one_month"] > 1:
                bits.append(f"{escape(str(t))}, whose last bucket holds {int(r['bucket_months'])} monthly cohorts, about "
                            f"{r['chargeoff_over_one_month']:.2f} times one of them ({r['min_share_not_aged']:.0%})")
        if bits:
            h.append("<p><b>Why conversion says nothing about rescue.</b> An account reaches the 180-day write-off only from the "
                     "last delinquency bucket of the month before, so if every charge-off had aged through delinquency a "
                     "month's charge-offs could not exceed what that bucket held. They do: " + "; ".join(bits) + ". The "
                     "prospectuses say why: accounts are written off at about 180 days late, or sooner when the cardholder is "
                     "bankrupt or has died. A conversion ratio therefore mixes aged and unaged losses in a proportion no "
                     "monthly report gives. A ratio above one is not evidence that an issuer's late accounts fare worse, and a "
                     "ratio below one is not evidence that they are rescued. Until November 2026 this page read American "
                     "Express's ratio as the opposite of protection and concluded that the answer was selection. That did "
                     "not follow, and for cards it is withdrawn. The check for every trust is on the "
                     "<a href='cards.html'>cards page</a>, section 5.</p>")
    if not sel.empty:
        names = ", ".join(sorted(sel["lender"]))
        lo, hi = sel["entry_share"].min(), sel["entry_share"].max()
        rr = ", ".join(f"{r['lender']} {r['roll_ratio']:.2f}" for _, r in sel.iterrows())
        below = att[att["lender"].isin(set(sel["lender"]))].groupby("lender")["roll_ratio"].agg(
            below=lambda x: int((x < 1).sum()), n="size")
        counts = ", ".join(f"{k} in {int(v['below'])} of {int(v['n'])}" for k, v in below.iterrows())
        h.append(f"<p><b>Autos, where the data is loan by loan.</b> Comparing lenders inside the same 20-point score bucket, "
                 f"{escape(names)} owe {lo:.0%} to {hi:.0%} of their advantage to entry: their borrowers are several times less "
                 f"likely to reach 30 days past due. Once past due the difference is smaller and uneven: median roll ratios "
                 f"against the baseline lender are {escape(rr)}, and the ratio is below one in these score buckets: "
                 f"{escape(counts)}. So most of the advantage is in not falling behind. For some lenders a smaller part is in "
                 f"what happens afterwards, which for a secured loan is as likely to be repossession and workout practice as "
                 f"the borrower's ranking of debts.</p>")
    if not rollers.empty:
        rr = "; ".join(f"{r['lender']}: entry ratio {r['entry_ratio']:.2f}, roll ratio {r['roll_ratio']:.2f}" for _, r in rollers.iterrows())
        h.append(f"<p><b>One instructive exception.</b> {escape(rr)}. Its borrowers fall behind at about the same rate as the "
                 f"baseline lender's but default more often afterwards. That is a difference in what happens after trouble "
                 f"starts, and the likelier readings are again repossession policy and workout practice.</p>")
    if direction and (direction.get("regime") or direction.get("tightenings")):
        best_name = str(best_c["trust"]) if best_c is not None else None
        h.append("<p><b>A test on direction rather than level.</b> If people rank their debts, the ranking should bite "
                 "hardest when money is short, so a protected card's conversion ratio should <i>fall</i> when delinquency is "
                 "high. " + " ".join(direction_sentences(direction, best_name)) + "</p>")
        if not regimes.empty:
            w = regimes.pivot_table(index="trust", columns="regime", values="conversion_ratio").reindex(columns=["loose", "tight"])
            w["move"] = w["tight"] - w["loose"]
            h.append(table(w.reset_index(), fmt={"loose": "{:.2f}", "tight": "{:.2f}", "move": "{:+.2f}"}))

    h.append("<h2>What else the data shows</h2>")
    if amt is not None and pti is not None and ltv is not None:
        h.append("<p><b>In these auto pools the payment carries the risk, not the size of the loan.</b> At the same score, lender "
                 "and origination quarter, comparing the top quintile against the bottom:</p>")
        rows = pd.DataFrame([
            {"factor": "loan amount", "odds_ratio": amt["odds_ratio"], "lo95": amt["lo95"], "hi95": amt["hi95"]},
            {"factor": "payment-to-income", "odds_ratio": pti["odds_ratio"], "lo95": pti["lo95"], "hi95": pti["hi95"]},
            {"factor": "loan-to-value", "odds_ratio": ltv["odds_ratio"], "lo95": ltv["lo95"], "hi95": ltv["hi95"]},
        ])
        h.append(table(rows, fmt={"odds_ratio": "{:.2f}", "lo95": "{:.2f}", "hi95": "{:.2f}"}))
        h.append(f"<p>A bigger loan at the same burden defaults <i>less</i> ({amt['odds_ratio']:.2f}), because at a fixed payment "
                 f"and a fixed loan-to-value a larger balance means a larger income behind it. What goes with more default is "
                 f"the monthly burden ({pti['odds_ratio']:.2f}) and lending past the value of the collateral "
                 f"({ltv['odds_ratio']:.2f}). These compare loans that differ in one recorded field. They are not the effect "
                 f"of lending the same borrower more, and they say nothing about card limits, which no data here observes.</p>")
    if not rank.empty and not flip.empty:
        held = ends_clause(e, noun="gap")
        prod_note = ""
        if not product.empty:
            bl = product[product["calibration"] == "prospectus_blend"]
            pl = product[product["calibration"] == "private_label"]
            if not bl.empty:
                t_name = str(bl["trust"].iloc[0])
                w = float(bl["private_label_share"].iloc[0])
                pl_g = pl["mean_residual_gross"].dropna()
                prod_note = (f" Each trust is calibrated to its prospectus product mix ({w:.1%} private label at "
                             f"{escape(t_name)}, general purpose elsewhere)"
                             + (f"; treating {escape(t_name)} wholly as private label reverses its gross sign under "
                                f"every curve ({pl_g.min():+.2%} to {pl_g.max():+.2%})." if not pl_g.empty and (pl_g < 0).all() else "."))
        h.append(f"<p><b>How much of an issuer's loss rate is its customer mix is unknown.</b> Predicting each trust's "
                 f"losses from its own score mix needs a loss curve by score, and no public source publishes one for cards. The four "
                 f"published curves that exist disagree by about five times. {held}, and {len(flip)} of {len(res)} trusts "
                 f"change the <i>sign</i> of their gap depending on which curve is assumed.{prod_note} The size of anyone's gap is not a "
                 f"finding.</p>")

    h.append("<h2>What this cannot say</h2>")
    h.append("<p>It cannot say whether a low-loss issuer's late accounts are rescued more or less often than anyone else's. That "
             "is the one place the two stories differ, and the monthly reports do not show it. The prospectuses do state each "
             "issuer's charge-off policy, about 180 days late or sooner on bankruptcy or death, but no report splits the "
             "charge-offs that aged through delinquency from the ones written off early, and an issuer that charges off "
             "faster or re-ages less would move the same numbers.</p>")
    h.append("<p>Nothing here observes one person holding two accounts. That is the measurement payment hierarchy actually requires, "
             "and it does not exist in public data: Regulation AB II exempted credit card securitisations from loan-level disclosure, "
             "and the credit panels that could answer it are confidential. Anyone claiming to have measured hierarchy from public "
             "filings has measured something else.</p>")
    h.append("<p>Three further limits, stated rather than buried. Trust pools are the securitised, seasoned end of an issuer's book "
             "and not the book. Lenders report different score models on different scales, and choose which loans go into a "
             "public pool, so the same score is not quite the same borrower from one lender to the next. And the regression "
             "discontinuity designs at lenders' own pricing cutoffs returned "
             "mostly nulls: half the candidate cutoffs failed a density test, meaning the applicant pool changes at the line, and the "
             "survivors were underpowered.</p>")

    h.append("<h2>The short version</h2>")
    short = "Issuers with low losses have far fewer accounts that fall behind, in cards and in auto loans."
    if best_c is not None:
        short += (f" {best_c['trust']}'s share of balances 30 days late is {best_c['entry_ratio']:.2f} times {base_c}'s, and its "
                  f"loss rate is {best_c['co_monthly_ratio']:.2f} times.")
    short += (" Both stories predict that. They differ on what happens to an account once it is late, and public card filings "
              "do not show it, so these filings do not answer the question in the title.")
    if not sel.empty:
        short += (" In auto loans, where each loan can be followed, the prime lenders' advantage at the same score is mostly "
                  "fewer loans falling behind, and for some of them a smaller part is in how late loans end.")
    h.append(f"<p>{short}</p>")
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
