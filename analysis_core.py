from pathlib import Path
import subprocess

try:
    import numpy as np
    import pandas as pd
    import matplotlib.pyplot as plt
except ImportError as exc:
    raise SystemExit("Missing Python packages. Install them with: pip install -r requirements.txt") from exc

ROOT = Path(__file__).resolve().parent
DATA_DIR, OUTPUT_DIR, FIGURE_DIR = ROOT / "data", ROOT / "outputs", ROOT / "figures"
REPORT_FILE = ROOT / "report.md"
POPULATION_FILE = DATA_DIR / "nonresponse_population.csv.gz"
POPULATION_SIZE, SAMPLE_SIZE, SEED = 50_000, 6_000, 20260812
AGE_BANDS = ["18-24", "25-34", "35-44", "45-54", "55-64", "65-74"]
REGIONS = ["London", "South", "Midlands", "North", "Scotland/Wales"]
GENDERS = ["Woman", "Man", "Non-binary / other"]
BG, TEXT, MUTED = "#000000", "#FFFFFF", "#B3B3B3"
LINE, GRID, BAR, ACCENT = "#404040", "#333333", "#666666", "#FFFFFF"


def run_git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True)


def check_repository_up_to_date():
    inside = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=ROOT, capture_output=True, text=True)
    if inside.returncode or inside.stdout.strip() != "true":
        print("GitHub remote not detected; running analysis without repository sync.")
        return False
    origin = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True, text=True)
    if origin.returncode:
        print("GitHub remote not detected; running analysis without repository sync.")
        return False
    branch = run_git("branch", "--show-current").stdout.strip()
    head = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=ROOT, capture_output=True)
    if not branch or head.returncode:
        print("Remote branch not initialized; running analysis without repository sync.")
        return False
    run_git("fetch", "origin")
    verify = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"origin/{branch}"], cwd=ROOT)
    if not branch or verify.returncode:
        print("Remote branch not initialized; running analysis without repository sync.")
        return False
    local_only, remote_only = map(int, run_git("rev-list", "--left-right", "--count", f"HEAD...origin/{branch}").stdout.split())
    if remote_only:
        raise SystemExit(f"Your Codespace is {remote_only} commit(s) behind origin/{branch}.\nRun: git pull --ff-only\nThen run: python analysis.py")
    print(f"Repository is up to date with origin/{branch}.")
    return True


def save_generated_files(sync):
    if not sync:
        return
    paths = ["report.md", "data/nonresponse_population.csv.gz", "data/nonresponse_codebook.csv", "data/nonresponse_scenario.csv", "outputs", "figures"]
    run_git("add", "--", *paths)
    changed = subprocess.run(["git", "diff", "--cached", "--quiet", "--", *paths], cwd=ROOT).returncode
    if changed == 0:
        print("No generated changes to commit.")
        return
    if changed != 1:
        raise SystemExit("Could not determine whether generated files changed.")
    run_git("commit", "-m", "Update nonresponse bias assessment results", "--", *paths)
    branch = run_git("branch", "--show-current").stdout.strip()
    run_git("push", "origin", branch)
    print(f"Generated files committed and pushed to origin/{branch}.")


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def ensure_population():
    if POPULATION_FILE.exists():
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    age = rng.choice(AGE_BANDS, POPULATION_SIZE, p=[.12, .20, .19, .18, .17, .14])
    region = rng.choice(REGIONS, POPULATION_SIZE, p=[.13, .25, .21, .27, .14])
    gender = rng.choice(GENDERS, POPULATION_SIZE, p=[.50, .48, .02])
    education = rng.choice(["Degree", "No degree"], POPULATION_SIZE, p=[.43, .57])
    digital = np.clip(np.round(62 + np.array([{"18-24":15,"25-34":11,"35-44":5,"45-54":-3,"55-64":-12,"65-74":-21}[x] for x in age]) + np.where(region == "London", 5, 0) + rng.normal(0, 13, POPULATION_SIZE), 1), 0, 100)
    wellbeing = np.clip(np.round(6.0 + np.array([{"18-24":-.5,"25-34":-.2,"35-44":0,"45-54":.2,"55-64":.4,"65-74":.6}[x] for x in age]) + np.where(education == "Degree", .25, -.1) + rng.normal(0, 1.45, POPULATION_SIZE), 1), 0, 10)
    support = np.clip(np.round(4.0 + .28 * wellbeing + .013 * digital + np.where(education == "Degree", .3, -.1) + rng.normal(0, 1.5, POPULATION_SIZE), 1), 0, 10)
    propensity = sigmoid(-2.05 + .024 * (digital - 50) + .16 * (wellbeing - 5) + np.where(education == "Degree", .40, -.15) + np.where(age == "65-74", -.30, 0) + np.where(region == "London", .15, 0))
    responded = rng.random(POPULATION_SIZE) < propensity
    population = pd.DataFrame({
        "person_id": [f"P{x:05d}" for x in range(1, POPULATION_SIZE + 1)], "age_band": age,
        "gender": gender, "region": region, "education": education,
        "digital_engagement_score": digital, "wellbeing_0_10": wellbeing,
        "service_support_0_10": support, "response_propensity": np.round(propensity, 4),
        "responded": responded.astype(int),
    })
    # Fixed invitation sample keeps the response analysis realistic and reproducible.
    invited = rng.choice(population.index, SAMPLE_SIZE, replace=False)
    population["invited"] = 0
    population.loc[invited, "invited"] = 1
    population.to_csv(POPULATION_FILE, index=False, compression="gzip")
    pd.DataFrame([
        ["person_id", "Synthetic person identifier"], ["age_band", "Age category"], ["gender", "Gender category"],
        ["region", "UK region category"], ["education", "Degree status"], ["digital_engagement_score", "Simulated digital engagement, 0-100"],
        ["wellbeing_0_10", "Simulated wellbeing score"], ["service_support_0_10", "Primary survey outcome"],
        ["response_propensity", "Modelled probability of response"], ["responded", "Response indicator"], ["invited", "Invitation-sample indicator"],
    ], columns=["variable", "description"]).to_csv(DATA_DIR / "nonresponse_codebook.csv", index=False)
    pd.DataFrame({"parameter": ["population_size", "invitation_sample_size", "seed", "weighting_controls"], "value": [POPULATION_SIZE, SAMPLE_SIZE, SEED, "age_band + region + education"]}).to_csv(DATA_DIR / "nonresponse_scenario.csv", index=False)


def load_population():
    frame = pd.read_csv(POPULATION_FILE)
    required = {"person_id", "age_band", "gender", "region", "education", "service_support_0_10", "responded", "invited"}
    missing = required - set(frame.columns)
    if missing or frame.person_id.duplicated().any() or not frame.responded.isin([0, 1]).all():
        raise ValueError(f"Population validation failed; missing={sorted(missing)}")
    return frame


def rake_weights(respondents, population, variables, iterations=40, cap=5.0):
    weights = pd.Series(1.0, index=respondents.index)
    for _ in range(iterations):
        old = weights.copy()
        for variable in variables:
            targets = population[variable].value_counts(normalize=True)
            current = weights.groupby(respondents[variable]).sum() / weights.sum()
            factors = (targets / current).replace([np.inf, -np.inf], np.nan).fillna(1)
            weights *= respondents[variable].map(factors).astype(float)
        weights = weights.clip(1 / cap, cap)
        weights *= len(weights) / weights.sum()
        if np.max(np.abs(weights - old)) < 1e-7:
            break
    return weights


def analyse(population):
    invited = population[population.invited.eq(1)].copy()
    respondents = invited[invited.responded.eq(1)].copy()
    respondents["weight"] = rake_weights(respondents, population, ["age_band", "region", "education"])
    pop_mean = population.service_support_0_10.mean()
    unweighted = respondents.service_support_0_10.mean()
    weighted = np.average(respondents.service_support_0_10, weights=respondents.weight)
    estimates = pd.DataFrame([
        ["Population benchmark", pop_mean, 0.0], ["Unweighted respondents", unweighted, unweighted-pop_mean],
        ["Raked respondents", weighted, weighted-pop_mean],
    ], columns=["estimate", "mean_service_support", "bias"])
    response_rows, composition_rows = [], []
    for variable in ["age_band", "gender", "region", "education"]:
        for category, group in invited.groupby(variable, sort=False):
            response_rows.append([variable, category, len(group), int(group.responded.sum()), group.responded.mean()])
        categories = population[variable].value_counts(normalize=True).index
        for category in categories:
            pop_share = population[variable].eq(category).mean()
            raw_share = respondents[variable].eq(category).mean()
            weighted_share = respondents.loc[respondents[variable].eq(category), "weight"].sum() / respondents.weight.sum()
            composition_rows.append([variable, category, pop_share, raw_share, weighted_share, (raw_share-pop_share)*100, (weighted_share-pop_share)*100])
    response = pd.DataFrame(response_rows, columns=["variable", "category", "invited", "respondents", "response_rate"])
    composition = pd.DataFrame(composition_rows, columns=["variable", "category", "population_share", "unweighted_share", "weighted_share", "unweighted_difference_pp", "weighted_difference_pp"])
    subgroup = respondents.groupby(["age_band", "education"], observed=True).apply(lambda x: pd.Series({"respondents": len(x), "unweighted_mean": x.service_support_0_10.mean(), "weighted_mean": np.average(x.service_support_0_10, weights=x.weight)}), include_groups=False).reset_index()
    ess = respondents.weight.sum() ** 2 / np.square(respondents.weight).sum()
    diagnostics = pd.DataFrame({"metric": ["Invitations", "Respondents", "Overall response rate", "Minimum weight", "Maximum weight", "Effective sample size", "Design effect", "Absolute bias reduction"], "value": [len(invited), len(respondents), len(respondents)/len(invited), respondents.weight.min(), respondents.weight.max(), ess, len(respondents)/ess, abs(unweighted-pop_mean)-abs(weighted-pop_mean)]})
    return invited, respondents, estimates, response, composition, subgroup, diagnostics


def style(ax, axis):
    ax.figure.patch.set_facecolor(BG); ax.set_facecolor(BG); ax.tick_params(colors=MUTED, labelsize=9.5, length=0, pad=7)
    ax.xaxis.label.set_color(MUTED); ax.yaxis.label.set_color(MUTED); ax.title.set_color(TEXT)
    for spine in ax.spines.values(): spine.set_visible(False)
    ax.grid(axis=axis, color=GRID, linewidth=.8); ax.set_axisbelow(True)


def create_figures(response, composition, estimates):
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    age = response[response.variable.eq("age_band")].set_index("category").reindex(AGE_BANDS)
    fig, ax = plt.subplots(figsize=(9.6, 5.6)); style(ax, "x")
    bars = ax.barh(age.index, age.response_rate*100, color=BAR, edgecolor=LINE, height=.6)
    ax.set_xlabel("Response rate (%)", labelpad=12); ax.set_title("Response rates vary by age", loc="left", pad=18, fontsize=16, fontweight=400, color=TEXT)
    for bar, value in zip(bars, age.response_rate*100): ax.text(value+.4, bar.get_y()+bar.get_height()/2, f"{value:.1f}%", va="center", color=TEXT)
    fig.tight_layout(pad=1.6); fig.savefig(FIGURE_DIR / "response_rate_by_age.png", dpi=200, facecolor=BG, bbox_inches="tight"); plt.close(fig)
    deviation = composition.groupby("variable")[["unweighted_difference_pp", "weighted_difference_pp"]].apply(lambda x: x.abs().mean())
    fig, ax = plt.subplots(figsize=(9.6, 5.6)); style(ax, "y")
    x=np.arange(len(deviation)); width=.34
    ax.bar(x-width/2, deviation.unweighted_difference_pp, width, color=BAR, edgecolor=LINE, label="Unweighted")
    ax.bar(x+width/2, deviation.weighted_difference_pp, width, color=ACCENT, edgecolor=LINE, label="Weighted")
    ax.set_xticks(x, [v.replace("_", " ").title() for v in deviation.index]); ax.set_ylabel("Average absolute deviation (pp)", labelpad=12)
    ax.set_title("Weighting improves population alignment", loc="left", pad=18, fontsize=16, fontweight=400, color=TEXT)
    legend=ax.legend(frameon=False); [t.set_color(MUTED) for t in legend.get_texts()]
    fig.tight_layout(pad=1.6); fig.savefig(FIGURE_DIR / "composition_deviation_before_after_weighting.png", dpi=200, facecolor=BG, bbox_inches="tight"); plt.close(fig)
    fig, ax = plt.subplots(figsize=(9.6, 5.6)); style(ax, "y")
    labels=estimates.estimate.tolist(); values=estimates.mean_service_support.tolist(); colors=[ACCENT, BAR, MUTED]
    bars=ax.bar(labels, values, color=colors, edgecolor=LINE, width=.58); ax.set_ylim(min(values)-.3, max(values)+.3); ax.set_ylabel("Mean service support (0-10)", labelpad=12)
    ax.set_title("Weighting reduces outcome bias", loc="left", pad=18, fontsize=16, fontweight=400, color=TEXT)
    for bar,value in zip(bars,values): ax.text(bar.get_x()+bar.get_width()/2,value+.025,f"{value:.3f}",ha="center",color=TEXT)
    fig.tight_layout(pad=1.6); fig.savefig(FIGURE_DIR / "estimate_bias_before_after_weighting.png", dpi=200, facecolor=BG, bbox_inches="tight"); plt.close(fig)


def generate_report(population, respondents, estimates, response, composition, diagnostics):
    lookup=estimates.set_index("estimate").mean_service_support
    pop, raw, weighted=lookup["Population benchmark"], lookup["Unweighted respondents"], lookup["Raked respondents"]
    reduction=(abs(raw-pop)-abs(weighted-pop))/abs(raw-pop)*100
    response_rate=len(respondents)/int(diagnostics.loc[diagnostics.metric.eq("Invitations"),"value"].iloc[0])
    ess=diagnostics.loc[diagnostics.metric.eq("Effective sample size"),"value"].iloc[0]
    rates=response.sort_values("response_rate").iloc[[0,-1]]
    report=f"""# Nonresponse Bias Assessment

## Project Snapshot

| Project type | Dataset | Tools | Outputs |
|---|---|---|---|
| Simulated Quantitative Case Study | {len(population):,}-Person Synthetic UK Adult Population | Python / Pandas / NumPy / Matplotlib | Response-Rate Tables; Composition Audit; Weighted Estimates; Diagnostics; Dark Figures |

**Skills demonstrated:** Sampling · Statistical Analysis · Data Validation · Data Weighting · Cross-tabulation

## Study Context

This simulated case study evaluates nonresponse in a hypothetical UK public-service survey. A known synthetic population makes the true outcome available, while {int(diagnostics.iloc[0].value):,} people are invited and response depends on demographic and behavioural characteristics. All values are synthetic and are not estimates of the real UK population.

## Objective and Method

The analysis measures subgroup response rates, compares respondent composition with the population, quantifies bias in mean service support, and applies iterative proportional fitting (raking) to age band, region and education margins. Weight trimming limits extreme weights to protect precision.

## Response Pattern

The invitation sample produced {len(respondents):,} respondents, an overall response rate of {response_rate*100:.1f}%. The lowest observed subgroup rate was {rates.iloc[0].category} ({rates.iloc[0].response_rate*100:.1f}%) and the highest was {rates.iloc[1].category} ({rates.iloc[1].response_rate*100:.1f}%). Because response propensity is also related to the survey outcome, the respondent mean is not representative without adjustment.

## Bias Assessment

| Estimate | Mean service support | Bias versus population |
|---|---:|---:|
| Population benchmark | {pop:.3f} | — |
| Unweighted respondents | {raw:.3f} | {raw-pop:+.3f} |
| Raked respondents | {weighted:.3f} | {weighted-pop:+.3f} |

Weighting reduced absolute bias by {reduction:.1f}%. The remaining bias is residual because raking aligns observed demographic controls but cannot fully correct selection on wellbeing and digital engagement. The weighted effective sample size is {ess:,.0f}, compared with {len(respondents):,} completed interviews.

## Interpretation

The exercise separates three ideas that are often conflated: response rate, demographic representativeness and outcome bias. A sample can have an acceptable overall response rate while still overrepresenting groups with systematically different outcomes. Weighting substantially improves measured composition and reduces bias, but the residual difference from the known benchmark demonstrates why weighting is an adjustment rather than proof of unbiasedness.

## Figures

### Response rates by age

![Response rates by age](figures/response_rate_by_age.png)

### Composition before and after weighting

![Composition deviation](figures/composition_deviation_before_after_weighting.png)

### Outcome estimate before and after weighting

![Estimate bias](figures/estimate_bias_before_after_weighting.png)

## Project Files

- [`data/nonresponse_population.csv.gz`](data/nonresponse_population.csv.gz) — compressed CSV containing the known synthetic population, invitation and response indicators.
- [`data/nonresponse_codebook.csv`](data/nonresponse_codebook.csv) — variable definitions.
- [`data/nonresponse_scenario.csv`](data/nonresponse_scenario.csv) — simulation parameters.
- [`outputs/respondents_weighted.csv`](outputs/respondents_weighted.csv) — respondent-level analysis file and final weights.
- [`outputs/response_rates_by_subgroup.csv`](outputs/response_rates_by_subgroup.csv) — subgroup response cross-tabulations.
- [`outputs/composition_before_after_weighting.csv`](outputs/composition_before_after_weighting.csv) — population, raw and weighted shares.
- [`outputs/estimate_bias_summary.csv`](outputs/estimate_bias_summary.csv) — benchmark, unweighted and weighted estimates.
- [`outputs/weighting_diagnostics.csv`](outputs/weighting_diagnostics.csv) — weight range, design effect and effective sample size.
- [`outputs/weighted_subgroup_estimates.csv`](outputs/weighted_subgroup_estimates.csv) — age-by-education estimates.
"""
    REPORT_FILE.write_text(report.strip()+"\n", encoding="utf-8")


def main():
    sync=check_repository_up_to_date(); OUTPUT_DIR.mkdir(parents=True, exist_ok=True); ensure_population(); population=load_population()
    invited, respondents, estimates, response, composition, subgroup, diagnostics=analyse(population)
    respondents.to_csv(OUTPUT_DIR/"respondents_weighted.csv", index=False)
    response.to_csv(OUTPUT_DIR/"response_rates_by_subgroup.csv", index=False)
    composition.to_csv(OUTPUT_DIR/"composition_before_after_weighting.csv", index=False)
    estimates.to_csv(OUTPUT_DIR/"estimate_bias_summary.csv", index=False)
    subgroup.to_csv(OUTPUT_DIR/"weighted_subgroup_estimates.csv", index=False)
    diagnostics.to_csv(OUTPUT_DIR/"weighting_diagnostics.csv", index=False)
    create_figures(response, composition, estimates); generate_report(population, respondents, estimates, response, composition, diagnostics)
    print("Nonresponse Bias Assessment\n===========================")
    print(f"Population loaded: {len(population):,}\nInvitations: {len(invited):,}\nRespondents: {len(respondents):,}\nResponse rate: {len(respondents)/len(invited):.1%}")
    for _,row in estimates.iterrows(): print(f"  {row.estimate}: {row.mean_service_support:.3f} (bias {row.bias:+.3f})")
    print("\nReport written to: report.md\nOutputs saved to: outputs/\nFigures saved to: figures/")
    save_generated_files(sync)


if __name__ == "__main__": main()
