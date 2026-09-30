"""
Kate engine: turns customer signals into one explainable recommendation.

Same logic as the web demo (index.html), ported to Python so it can run
on a server. Pure functions, no I/O: easy to test and easy to audit.

Pipeline:  signals -> understand() -> recommend() -> Recommendation
"""
from __future__ import annotations

from dataclasses import dataclass, field


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# --------------------------------------------------------------------------
# 1. Data model
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Pathway:
    n: int
    key: str
    name: str
    product: str
    risk: int | None          # 1-7 indicative risk, None for insurance/loans
    boundary: str             # "keep in mind" text shown to the customer


PATHWAYS = {p.key: p for p in [
    Pathway(1, "cash", "Accessible cash", "KBC Savings Account", 1,
            "Do not lock up money needed for near-term expenses."),
    Pathway(2, "gov", "Government bonds", "Government bonds via Bolero", 2,
            "Price can fall if sold before maturity."),
    Pathway(3, "corp", "Corporate bonds", "Corporate bonds via Bolero", 3,
            "The issuer could fail to pay."),
    Pathway(4, "equity", "Global equities", "Diversified equity fund", 4,
            "Value can fall; check the specific fund's holdings."),
    Pathway(5, "realestate", "Real-estate exposure", "Listed real-estate share via Bolero", 5,
            "A single share is not diversified property exposure."),
    Pathway(6, "homeins", "Home protection", "KBC Home Insurance", None,
            "Cover and exclusions depend on the policy."),
    Pathway(7, "loanins", "Mortgage protection", "KBC Comfort Loan Balance Insurance", None,
            "Linked to the outstanding loan and the agreed cover percentage."),
    Pathway(8, "mortgage", "Home financing", "KBC Mortgage Loan", None,
            "Subject to assessment and approval."),
]}


@dataclass
class Signals:
    income: float
    income_months: int
    expenses: float
    savings: float
    invested: float
    portfolio_sri: int
    questionnaire: int          # 1-5, from the MiFID risk questionnaire
    knowledge: int              # 1-3
    reads_market_news: bool
    prefers_advisor: bool
    products: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)


@dataclass
class Customer:
    id: str
    first_name: str
    formal_name: str
    age: int
    personalised: bool          # consent toggle: False -> Kate uses no data
    signals: Signals


@dataclass
class Understanding:
    surplus: float
    buffer_months: float
    capacity: int               # 0-100
    max_sri: int                # personal risk limit, 1-7
    knowledge: int              # 0-100
    tone: str                   # casual | warm | analytical | formal


@dataclass
class Recommendation:
    pathway: Pathway
    title: str
    body: str
    cta: str
    reasons: list[str]
    tone: str
    max_sri: int


# --------------------------------------------------------------------------
# 2. Understand: explainable scoring
# --------------------------------------------------------------------------
def understand(c: Customer) -> Understanding:
    s = c.signals
    surplus = s.income - s.expenses
    savings_rate = surplus / s.income
    buffer = s.savings / s.expenses
    horizon = max(1, 65 - c.age)

    capacity = round(100 * (
        0.35 * clamp(buffer / 6) +
        0.25 * clamp(s.income_months / 24) +
        0.25 * clamp(horizon / 30) +
        0.15 * clamp(savings_rate / 0.25)))
    level = 1 if capacity < 35 else 2 if capacity < 50 else 3 if capacity < 65 else 4 if capacity < 80 else 5

    # Risk limit = lower of what they WANT and what they can BEAR.
    max_sri = min(s.questionnaire, level) + 1

    knowledge = min(100, s.knowledge * 25 + (15 if s.reads_market_news else 0) + (10 if s.invested > 0 else 0))

    if c.age >= 60 or s.prefers_advisor:
        tone = "formal"
    elif knowledge >= 75 and s.reads_market_news:
        tone = "analytical"
    elif "child" in s.events or "home" in s.events:
        tone = "warm"
    else:
        tone = "casual"

    return Understanding(surplus, buffer, capacity, max_sri, knowledge, tone)


# --------------------------------------------------------------------------
# 3. Next best actions (a subset of the demo, same structure)
#    Each action: when it applies, priority, pathway, reasons, copy.
# --------------------------------------------------------------------------
ACTIONS = [
    dict(id="phaseBonus", pathway="equity", score=95,
         when=lambda c, s, u: "bonus" in s.events,
         reasons=lambda c, s, u: ["A one-off deposit arrived on your savings account",
                                  "Spreading the entry over 6 months lowers timing risk",
                                  f"A diversified equity fund fits your risk limit of {u.max_sri} of 7"],
         copy=lambda c, s, u: ("15.000 euros received: 3 options",
                               "Invest in 6 monthly steps, invest it all now, or keep it in savings.",
                               "Compare the 3 options")),
    dict(id="pensionIncome", pathway="gov", score=94,
         when=lambda c, s, u: "pension" in s.events,
         reasons=lambda c, s, u: ["Your pension date was confirmed",
                                  "Bonds maturing around that date match a known horizon"],
         copy=lambda c, s, u: ("Your income after retirement",
                               f"Dear {c.formal_name}, your adviser can prepare an income overview.",
                               "Request my income overview")),
    dict(id="raisePlan", pathway="equity", score=92,
         when=lambda c, s, u: "raise" in s.events,
         reasons=lambda c, s, u: ["Your salary went up",
                                  f"Your risk capacity is now {u.capacity} of 100",
                                  f"Your risk limit is {u.max_sri} of 7, so an equity fund fits"],
         copy=lambda c, s, u: ("Nice raise! Let some of it work for you",
                               "Put 50 euros a month into a diversified equity fund and 80 euros extra into savings?",
                               "Set it up in 2 taps")),
    dict(id="eduPlan", pathway="equity", score=90,
         when=lambda c, s, u: "child" in s.events,
         reasons=lambda c, s, u: ["A new child in the household",
                                  "An 18-year horizon suits long-term growth"],
         copy=lambda c, s, u: ("A head start for your little one",
                               "Setting aside 50 euros a month until they turn 18 can build a meaningful fund.",
                               "Start a monthly plan")),
    dict(id="buffer", pathway="cash", score=84,
         when=lambda c, s, u: u.buffer_months < 3,
         reasons=lambda c, s, u: [f"Savings cover {u.buffer_months:.1f} months of spending, below 3",
                                  "A safety net comes before investing"],
         copy=lambda c, s, u: (f"Your safety net: {u.buffer_months:.1f} months",
                               "Three months of spending is a comfortable cushion.",
                               "Adjust auto-save")),
]


def recommend(c: Customer, limit: int = 3) -> list[Recommendation]:
    """Top suggestions, one per pathway, never above the customer's risk limit."""
    if not c.personalised:
        return []                                   # consent off: no personal data used

    s, u = c.signals, understand(c)
    out, used = [], set()
    for a in sorted(ACTIONS, key=lambda a: -a["score"]):
        if len(out) >= limit or not a["when"](c, s, u):
            continue
        p = PATHWAYS[a["pathway"]]
        if p.key in used:
            continue
        if p.risk is not None and p.risk > u.max_sri:   # SUITABILITY GATE
            continue
        used.add(p.key)
        title, body, cta = a["copy"](c, s, u)
        out.append(Recommendation(p, title, body, cta, a["reasons"](c, s, u), u.tone, u.max_sri))
    return out


# --------------------------------------------------------------------------
# 4. Synthetic customers (no real data)
# --------------------------------------------------------------------------
DEMO_CUSTOMERS = {
    "lotte": Customer("lotte", "Lotte", "Ms Janssens", 23, True, Signals(
        income=2410, income_months=4, expenses=1750, savings=2100, invested=0, portfolio_sri=0,
        questionnaire=3, knowledge=1, reads_market_news=False, prefers_advisor=False,
        products=["Current account", "Credit card"], events=["raise"])),
    "ahmed": Customer("ahmed", "Ahmed", "Mr El Amrani", 34, True, Signals(
        income=4380, income_months=60, expenses=3450, savings=15500, invested=0, portfolio_sri=0,
        questionnaire=3, knowledge=1, reads_market_news=False, prefers_advisor=False,
        products=["Current account", "Mortgage", "Home insurance"], events=["home", "child"])),
    "marc": Customer("marc", "Marc", "Mr Verhoeven", 47, True, Signals(
        income=6800, income_months=216, expenses=3900, savings=107000, invested=18000, portfolio_sri=4,
        questionnaire=4, knowledge=3, reads_market_news=True, prefers_advisor=False,
        products=["Current account", "Savings account", "Investment account"], events=["bonus"])),
    "anna": Customer("anna", "Anna", "Mrs Peeters", 63, True, Signals(
        income=3100, income_months=300, expenses=2400, savings=48000, invested=95000, portfolio_sri=5,
        questionnaire=2, knowledge=2, reads_market_news=False, prefers_advisor=True,
        products=["Current account", "Savings account", "Investment account"], events=["pension"])),
}
