"use client";

import { useState, useMemo } from "react";
import { Card, OutcomeBadge } from "@fiona/ui";

interface LaunchLabSimulatorProps {
  initialCurrency?: string;
  defaultCapitalMinor?: number;
}

export function LaunchLabSimulator({
  defaultCapitalMinor = 180_000_000, // PKR 1.8m
}: LaunchLabSimulatorProps) {
  // Base scenario defaults (Winter Shawl)
  const baseUnitCost = 3500; // PKR
  const basePrice = 7500; // PKR
  const baseDemand = 1200; // units over 6 months
  const marketingBudget = 350_000; // PKR total
  const monthlyOverhead = 85_000; // PKR / month
  const [availableCapital, setAvailableCapital] = useState<number>(defaultCapitalMinor / 100); // PKR 1.8m
  const horizonMonths = 6; // months

  // Interactive What-If adjustments
  const [priceShiftPct, setPriceShiftPct] = useState<number>(0); // -30% to +50%
  const [demandShiftPct, setDemandShiftPct] = useState<number>(0); // -50% to +80%
  const [marketingMultiplier, setMarketingMultiplier] = useState<number>(1.0); // 0.5x to 3x
  const [unitCostShiftPct, setUnitCostShiftPct] = useState<number>(0); // -20% to +40%
  const [batchSize, setBatchSize] = useState<number>(400); // Initial run

  // Recalculations
  const sim = useMemo(() => {
    const effPrice = Math.round(basePrice * (1 + priceShiftPct / 100));
    const effUnitCost = Math.round(baseUnitCost * (1 + unitCostShiftPct / 100));
    const unitContribution = effPrice - effUnitCost;
    const contributionMarginPct = effPrice > 0 ? (unitContribution / effPrice) * 100 : 0;

    // Price elasticity: every +10% price change reduces demand by ~8%
    const elasticityDampening = 1 - (priceShiftPct / 100) * 0.8;
    const effDemand = Math.max(
      10,
      Math.round(baseDemand * (1 + demandShiftPct / 100) * elasticityDampening)
    );

    const effMarketing = Math.round(marketingBudget * marketingMultiplier);
    const totalFixedCosts = effMarketing + monthlyOverhead * horizonMonths;

    // Break-even units = Total Fixed Costs / Unit Contribution
    const breakevenUnits = unitContribution > 0 ? Math.ceil(totalFixedCosts / unitContribution) : 99999;
    const breakevenRevenue = breakevenUnits * effPrice;

    // Peak cash need = Initial Batch Inventory Cost + Launch Marketing + Month 1 Overhead
    const initialInventoryCost = batchSize * effUnitCost;
    const peakCash = initialInventoryCost + effMarketing * 0.5 + monthlyOverhead * 2;

    // Projected revenue and profit
    const actualUnitsSold = Math.min(effDemand, batchSize * 2);
    const totalRevenue = actualUnitsSold * effPrice;
    const totalCogs = actualUnitsSold * effUnitCost;
    const grossProfit = totalRevenue - totalCogs;
    const netProfit = grossProfit - totalFixedCosts;

    // Payback month estimation
    let paybackMonth = 12;
    if (unitContribution > 0 && actualUnitsSold > 0) {
      const monthlyContribution = (actualUnitsSold * unitContribution) / horizonMonths;
      const netMonthlyCashflow = monthlyContribution - monthlyOverhead;
      if (netMonthlyCashflow > 0) {
        paybackMonth = Math.min(12, Math.max(1, Math.ceil(peakCash / netMonthlyCashflow)));
      }
    }

    // Rules Evaluation
    const rules = [
      {
        id: "LL-01",
        label: "Positive Unit Contribution",
        detail: `PKR ${unitContribution.toLocaleString()} per unit (Price: PKR ${effPrice.toLocaleString()}, Cost: PKR ${effUnitCost.toLocaleString()})`,
        passed: unitContribution > 0,
      },
      {
        id: "LL-02",
        label: "Contribution Margin ≥ 20.0%",
        detail: `Actual margin is ${contributionMarginPct.toFixed(1)}%`,
        passed: contributionMarginPct >= 20.0,
      },
      {
        id: "LL-03",
        label: `Payback within Horizon (≤ ${horizonMonths} mo)`,
        detail: `Est. payback in ${paybackMonth <= horizonMonths ? `${paybackMonth} months` : `> ${horizonMonths} months (Breached)`}`,
        passed: paybackMonth <= horizonMonths,
      },
      {
        id: "LL-04",
        label: "Peak Cash within Capital Reserve",
        detail: `Peak cash needed: PKR ${peakCash.toLocaleString()} vs Available: PKR ${availableCapital.toLocaleString()}`,
        passed: peakCash <= availableCapital,
      },
      {
        id: "LL-05",
        label: "Break-even within Forecast Demand",
        detail: `Break-even requires ${breakevenUnits} units (${((breakevenUnits / Math.max(1, effDemand)) * 100).toFixed(0)}% of expected demand)`,
        passed: breakevenUnits <= effDemand,
      },
    ];

    const failedCount = rules.filter((r) => !r.passed).length;

    let recommendation: {
      label: "LAUNCH" | "PILOT_FIRST" | "REVISE" | "NOT_RECOMMENDED";
      badge: "approve" | "conditions" | "escalate" | "block";
      description: string;
    };

    if (unitContribution <= 0 || netProfit < -availableCapital * 0.5) {
      recommendation = {
        label: "NOT_RECOMMENDED",
        badge: "block",
        description: "Negative unit economics or catastrophic loss exposure. Do not produce.",
      };
    } else if (failedCount >= 2) {
      recommendation = {
        label: "REVISE",
        badge: "escalate",
        description: "Multiple guardrail breaches (capital or horizon limit). Re-negotiate unit cost or adjust retail price before proceeding.",
      };
    } else if (failedCount === 1 || actualUnitsSold < breakevenUnits * 1.25) {
      recommendation = {
        label: "PILOT_FIRST",
        badge: "conditions",
        description: `Viable unit economics, but capital or demand buffer is tight. Recommend a restricted pilot batch of ${Math.min(batchSize, 250)} units first.`,
      };
    } else {
      recommendation = {
        label: "LAUNCH",
        badge: "approve",
        description: `Strong margins (${contributionMarginPct.toFixed(1)}%), break-even reached in month ${paybackMonth}, and peak cash is safely within the capital cap.`,
      };
    }

    return {
      effPrice,
      effUnitCost,
      unitContribution,
      contributionMarginPct,
      effDemand,
      breakevenUnits,
      breakevenRevenue,
      peakCash,
      actualUnitsSold,
      totalRevenue,
      netProfit,
      paybackMonth,
      rules,
      recommendation,
    };
  }, [
    basePrice,
    baseUnitCost,
    baseDemand,
    marketingBudget,
    monthlyOverhead,
    availableCapital,
    horizonMonths,
    priceShiftPct,
    demandShiftPct,
    marketingMultiplier,
    unitCostShiftPct,
    batchSize,
  ]);

  return (
    <div className="launch-lab-interactive">
      {/* Top Banner / Recommendation */}
      <Card className="tier-panel" style={{ borderLeft: "4px solid var(--accent)" }}>
        <div className="panel-heading">
          <div>
            <span className="eyebrow">YAHYA SIMULATION ENGINE · MONTE CARLO RESOLVER</span>
            <h2>Scenario Recommendation: {sim.recommendation.label.replaceAll("_", " ")}</h2>
          </div>
          <OutcomeBadge outcome={sim.recommendation.badge} />
        </div>
        <p className="proposal-reasoning" style={{ fontSize: "12px", color: "var(--text)" }}>
          {sim.recommendation.description}
        </p>
      </Card>

      {/* Metrics Row */}
      <div className="tier-metric-grid">
        <Card className="tier-metric">
          <span className="eyebrow">ESTIMATED PAYBACK</span>
          <strong>{sim.paybackMonth <= horizonMonths ? `Month ${sim.paybackMonth}` : "Breaches horizon"}</strong>
          <small>Owner horizon: {horizonMonths} months</small>
        </Card>
        <Card className="tier-metric">
          <span className="eyebrow">PEAK CASH DRAW</span>
          <strong className={sim.peakCash > availableCapital ? "money-negative" : ""}>
            PKR {sim.peakCash.toLocaleString()}
          </strong>
          <small>Cap: PKR {availableCapital.toLocaleString()}</small>
        </Card>
        <Card className="tier-metric">
          <span className="eyebrow">PROJECTED NET PROFIT</span>
          <strong className={sim.netProfit < 0 ? "money-negative" : "money-positive"}>
            PKR {sim.netProfit.toLocaleString()}
          </strong>
          <small>At {sim.actualUnitsSold} units sold</small>
        </Card>
      </div>

      {/* What-If Interactive Sliders */}
      <Card className="tier-panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">SENSITIVITY &amp; STRESS TEST</span>
            <h2>Interactive What-If Sliders</h2>
          </div>
          <span className="placeholder-tag">LIVE DYNAMIC MODEL</span>
        </div>

        <div className="simulator-controls-grid">
          <label className="slider-group">
            <div className="slider-label">
              <span>Price Shift: {priceShiftPct >= 0 ? `+${priceShiftPct}%` : `${priceShiftPct}%`}</span>
              <strong>PKR {sim.effPrice.toLocaleString()}</strong>
            </div>
            <input
              type="range"
              min="-30"
              max="50"
              step="5"
              value={priceShiftPct}
              onChange={(e) => setPriceShiftPct(Number(e.target.value))}
            />
            <small className="footnote">Base: PKR {basePrice.toLocaleString()} (reflects price elasticity)</small>
          </label>

          <label className="slider-group">
            <div className="slider-label">
              <span>Demand Shock: {demandShiftPct >= 0 ? `+${demandShiftPct}%` : `${demandShiftPct}%`}</span>
              <strong>{sim.effDemand} units</strong>
            </div>
            <input
              type="range"
              min="-50"
              max="80"
              step="5"
              value={demandShiftPct}
              onChange={(e) => setDemandShiftPct(Number(e.target.value))}
            />
            <small className="footnote">Base seasonal demand: {baseDemand} units</small>
          </label>

          <label className="slider-group">
            <div className="slider-label">
              <span>Marketing Multiplier: {marketingMultiplier.toFixed(1)}×</span>
              <strong>PKR {Math.round(marketingBudget * marketingMultiplier).toLocaleString()}</strong>
            </div>
            <input
              type="range"
              min="0.5"
              max="3.0"
              step="0.25"
              value={marketingMultiplier}
              onChange={(e) => setMarketingMultiplier(Number(e.target.value))}
            />
            <small className="footnote">Social ads, influencer seeding, photography</small>
          </label>

          <label className="slider-group">
            <div className="slider-label">
              <span>Unit Cost Variation: {unitCostShiftPct >= 0 ? `+${unitCostShiftPct}%` : `${unitCostShiftPct}%`}</span>
              <strong>PKR {sim.effUnitCost.toLocaleString()}</strong>
            </div>
            <input
              type="range"
              min="-20"
              max="40"
              step="5"
              value={unitCostShiftPct}
              onChange={(e) => setUnitCostShiftPct(Number(e.target.value))}
            />
            <small className="footnote">Raw wool inflation, dyeing &amp; tailoring labor</small>
          </label>

          <label className="slider-group">
            <div className="slider-label">
              <span>Initial Batch Production</span>
              <strong>{batchSize} units</strong>
            </div>
            <input
              type="range"
              min="100"
              max="1500"
              step="50"
              value={batchSize}
              onChange={(e) => setBatchSize(Number(e.target.value))}
            />
            <small className="footnote">First production run commitments</small>
          </label>

          <label className="slider-group">
            <div className="slider-label">
              <span>Capital Reserve Allocation</span>
              <strong>PKR {availableCapital.toLocaleString()}</strong>
            </div>
            <input
              type="range"
              min="500000"
              max="4000000"
              step="100000"
              value={availableCapital}
              onChange={(e) => setAvailableCapital(Number(e.target.value))}
            />
            <small className="footnote">Working capital limit for this SKU launch</small>
          </label>
        </div>
      </Card>

      {/* Break-even & Rule Checks */}
      <div className="launch-sub-grid">
        <Card className="tier-panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">UNIT ECONOMICS</span>
              <h2>Break-even &amp; Unit Margin</h2>
            </div>
            <span className="placeholder-tag">{sim.contributionMarginPct.toFixed(1)}% MARGIN</span>
          </div>
          <div className="breakeven-stats-list">
            <div className="breakeven-row">
              <span>Unit Selling Price</span>
              <strong>PKR {sim.effPrice.toLocaleString()}</strong>
            </div>
            <div className="breakeven-row">
              <span>Unit Direct Cost (COGS)</span>
              <strong>PKR {sim.effUnitCost.toLocaleString()}</strong>
            </div>
            <div className="breakeven-row">
              <span>Unit Contribution</span>
              <strong style={{ color: "var(--accent)" }}>PKR {sim.unitContribution.toLocaleString()}</strong>
            </div>
            <div className="breakeven-row">
              <span>Break-even Volume</span>
              <strong>{sim.breakevenUnits} units</strong>
            </div>
            <div className="breakeven-row">
              <span>Break-even Turnover</span>
              <strong>PKR {sim.breakevenRevenue.toLocaleString()}</strong>
            </div>
          </div>
        </Card>

        <Card className="tier-panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">GUARDIAN VERIFICATION</span>
              <h2>Launch Guardrail Checklist</h2>
            </div>
            <span className="placeholder-tag">5 CHECKS</span>
          </div>
          <ul className="rule-checklist">
            {sim.rules.map((rule) => (
              <li key={rule.id} className={`rule-item ${rule.passed ? "passed" : "failed"}`}>
                <span className="rule-icon" aria-hidden="true">
                  {rule.passed ? "✓" : "×"}
                </span>
                <div>
                  <strong>{rule.id} · {rule.label}</strong>
                  <p>{rule.detail}</p>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <p className="footnote">
        Launch Lab simulations synthesize tenant historical ledger trends, seasonal sales records, and stated owner assumptions. The simulation is purely advisory; no purchase order or manufacturing commitment is created.
      </p>
    </div>
  );
}
