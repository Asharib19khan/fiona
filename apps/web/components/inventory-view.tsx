"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Card, MoneyText } from "@fiona/ui";
import { Kpi, KpiGrid } from "@/components/screen-kit";
import { BoxIcon, GaugeIcon, TrendDownIcon } from "@/components/briefing-icons";

const PAGE = 20;

export interface InventoryItemData {
  sku: string;
  name: string;
  category: string;
  season: string;
  on_hand: number;
  unit_cost_minor: number;
  price_minor: number;
  stock_value_minor: number;
  units_sold_window: number;
  revenue_minor: number;
  gross_margin_bp: number;
  abc: "A" | "B" | "C";
  xyz: "X" | "Y" | "Z";
  movement: "fast" | "normal" | "slow" | "dead";
  days_of_cover: number;
  reorder_point: number;
  suggested_order_qty: number;
  lead_time_days: number;
  safety_stock: number;
}

export interface InventorySummaryData {
  stock_value_minor: number;
  dead_stock_value_minor: number;
  slow_stock_value_minor: number;
  sku_count: number;
  gmroi_bp: number;
}

interface InventoryViewProps {
  summary: InventorySummaryData;
  items: InventoryItemData[];
}

export function InventoryView({ summary, items }: InventoryViewProps) {
  const [filter, setFilter] = useState<"all" | "fast" | "normal" | "slow" | "dead">("all");
  const [selectedSku, setSelectedSku] = useState<string>(items[0]?.sku ?? "");
  const [setupCost, setSetupCost] = useState<number>(2500); // PKR
  const [holdingRate, setHoldingRate] = useState<number>(20); // 20% per year
  const [visible, setVisible] = useState(PAGE);
  const lab = useRef<HTMLDivElement>(null);
  const picked = useRef(false);

  // After someone picks an item, bring the EOQ calculator into view (it sits below the register).
  useEffect(() => {
    if (!picked.current) return;
    picked.current = false;
    lab.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [selectedSku]);

  function pick(sku: string) {
    picked.current = true;
    setSelectedSku(sku);
  }

  function chooseFilter(next: "all" | "fast" | "normal" | "slow" | "dead") {
    setFilter(next);
    setVisible(PAGE);
  }

  const filteredItems = useMemo(() => {
    if (filter === "all") return items;
    return items.filter((item) => item.movement === filter);
  }, [items, filter]);

  const activeItem = useMemo(() => {
    return items.find((i) => i.sku === selectedSku) ?? items[0];
  }, [items, selectedSku]);

  // Economic Order Quantity (EOQ) calculation
  // D = Annual demand (estimated from 90-day window: units_sold_window * 4)
  // S = Setup / ordering cost per order
  // H = Holding cost per unit/year = unit_cost * holdingRate / 100
  const eoqCalculation = useMemo(() => {
    if (!activeItem) return null;
    const annualDemand = Math.max(1, activeItem.units_sold_window * 4);
    const unitCost = activeItem.unit_cost_minor / 100;
    const holdingCostPerUnit = Math.max(1, unitCost * (holdingRate / 100));
    const eoq = Math.round(Math.sqrt((2 * annualDemand * setupCost) / holdingCostPerUnit));
    const ordersPerYear = (annualDemand / Math.max(1, eoq)).toFixed(1);
    const totalAnnualHoldingCost = (eoq / 2) * holdingCostPerUnit;
    const totalAnnualOrderingCost = (annualDemand / Math.max(1, eoq)) * setupCost;
    const totalCost = totalAnnualHoldingCost + totalAnnualOrderingCost;

    return {
      annualDemand,
      unitCost,
      holdingCostPerUnit,
      eoq: Math.max(1, eoq),
      ordersPerYear,
      totalCost,
    };
  }, [activeItem, setupCost, holdingRate]);

  // ABC-XYZ Matrix counts
  const matrix = useMemo(() => {
    const grid: Record<string, InventoryItemData[]> = {};
    for (const abc of ["A", "B", "C"] as const) {
      for (const xyz of ["X", "Y", "Z"] as const) {
        grid[`${abc}${xyz}`] = [];
      }
    }
    for (const item of items) {
      const key = `${item.abc}${item.xyz}`;
      if (grid[key]) grid[key].push(item);
    }
    return grid;
  }, [items]);

  return (
    <div className="inventory-view-interactive">
      {/* Metrics Row */}
      <KpiGrid label="Inventory summary">
        <Kpi index={1} label="Stock at cost" icon={<BoxIcon />} value={<MoneyText amountMinor={summary.stock_value_minor} />} note={`${summary.sku_count} active SKUs in catalogue`} />
        <Kpi index={2} label="Slow / dead capital" icon={<TrendDownIcon />} tone="danger" emphasis="negative" value={<MoneyText amountMinor={summary.slow_stock_value_minor + summary.dead_stock_value_minor} />} note={<>Slow: <MoneyText amountMinor={summary.slow_stock_value_minor} /> · Dead: <MoneyText amountMinor={summary.dead_stock_value_minor} /></>} />
        <Kpi index={3} label="Annualised GMROI" icon={<GaugeIcon />} tone="green" value={`${(summary.gmroi_bp / 100).toFixed(1)}%`} note="Gross margin return on inventory" />
      </KpiGrid>

      {/* ABC-XYZ Classification Matrix */}
      <Card className="tier-panel sk-panel">
        <div className="panel-heading sk-panel-heading">
          <div>
            <span className="eyebrow">PORTFOLIO CLASSIFICATION</span>
            <h2>ABC-XYZ Inventory Matrix</h2>
          </div>
          <span className="placeholder-tag">VALUE × DEMAND STABILITY</span>
        </div>
        <div className="matrix-explainer">
          <p>
            <strong>ABC</strong> ranks revenue share (A: 80% volume, B: 15%, C: 5%). <strong>XYZ</strong> measures demand predictability (X: steady, Y: variable, Z: erratic). High-priority cash resides in AX/AY; dead capital clusters in CZ.
          </p>
        </div>
        <div className="abc-xyz-grid">
          <div className="matrix-cell header-col"></div>
          <div className="matrix-cell header-col">X (Steady CV &lt; 50%)</div>
          <div className="matrix-cell header-col">Y (Variable CV 50-100%)</div>
          <div className="matrix-cell header-col">Z (Erratic CV &gt; 100%)</div>

          {(["A", "B", "C"] as const).map((abc) => (
            <div key={abc} className="matrix-row-group">
              <div className="matrix-cell row-label">
                <strong>{abc}</strong>
                <small>{abc === "A" ? "High Value (80%)" : abc === "B" ? "Mid Value (15%)" : "Low Value (5%)"}</small>
              </div>
              {(["X", "Y", "Z"] as const).map((xyz) => {
                const cellItems = matrix[`${abc}${xyz}`] ?? [];
                return (
                  <div
                    key={`${abc}${xyz}`}
                    className={`matrix-cell cell-body ${cellItems.length ? "cell-active" : "cell-empty"}`}
                  >
                    <span className="cell-code">{abc}{xyz}</span>
                    <span className="cell-count">{cellItems.length} SKU{cellItems.length === 1 ? "" : "s"}</span>
                    {cellItems.slice(0, 2).map((item) => (
                      <button
                        key={item.sku}
                        type="button"
                        className="cell-item-chip"
                        onClick={() => pick(item.sku)}
                        title={`${item.name} - ${item.movement}`}
                      >
                        {item.sku}
                      </button>
                    ))}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </Card>

      {/* Filter and Item Table */}
      <Card className="tier-panel sk-panel">
        <div className="panel-heading sk-panel-heading">
          <div>
            <span className="eyebrow">STOCK REGISTER</span>
            <h2>Stock Movement &amp; Coverage Analysis</h2>
          </div>
          <div className="filter-button-group">
            <button
              type="button"
              className={`filter-btn ${filter === "all" ? "active" : ""}`}
              onClick={() => chooseFilter("all")}
            >
              All ({items.length})
            </button>
            <button
              type="button"
              className={`filter-btn ${filter === "fast" ? "active" : ""}`}
              onClick={() => chooseFilter("fast")}
            >
              Fast ({items.filter((i) => i.movement === "fast").length})
            </button>
            <button
              type="button"
              className={`filter-btn ${filter === "normal" ? "active" : ""}`}
              onClick={() => chooseFilter("normal")}
            >
              Normal ({items.filter((i) => i.movement === "normal").length})
            </button>
            <button
              type="button"
              className={`filter-btn ${filter === "slow" ? "active" : ""}`}
              onClick={() => chooseFilter("slow")}
            >
              Slow ({items.filter((i) => i.movement === "slow").length})
            </button>
            <button
              type="button"
              className={`filter-btn ${filter === "dead" ? "active" : ""}`}
              onClick={() => chooseFilter("dead")}
            >
              Dead ({items.filter((i) => i.movement === "dead").length})
            </button>
          </div>
        </div>

        <div className="data-table-wrap sk-table-wrap">
          <table className="data-table sk-table inventory-table">
            <thead>
              <tr>
                <th>SKU / Name</th>
                <th>Movement</th>
                <th>Class</th>
                <th>On Hand</th>
                <th>Stock Value</th>
                <th>Days of Cover</th>
                <th>Gross Margin</th>
                <th>Reorder Suggestion</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredItems.slice(0, visible).map((item, index) => {
                const isSelected = item.sku === selectedSku;
                return (
                  <tr key={item.sku} className={`${isSelected ? "table-row-selected" : ""} ${index >= PAGE ? "sk-row-new" : ""}`.trim() || undefined}>
                    <td>
                      <strong>{item.sku}</strong>
                      <div className="table-subtext">{item.name}</div>
                    </td>
                    <td>
                      <span className={`movement-tag movement-${item.movement}`}>
                        {item.movement.charAt(0).toUpperCase() + item.movement.slice(1)}
                      </span>
                    </td>
                    <td>
                      <span className="badge-class">{item.abc}{item.xyz}</span>
                    </td>
                    <td>{item.on_hand} pcs</td>
                    <td className="is-num"><MoneyText amountMinor={item.stock_value_minor} animateCount={false} /></td>
                    <td>
                      <span className={item.days_of_cover > 180 ? "status-warning" : item.days_of_cover < 20 ? "status-warning" : ""}>
                        {item.days_of_cover} days
                      </span>
                    </td>
                    <td>{(item.gross_margin_bp / 100).toFixed(1)}%</td>
                    <td>
                      {item.suggested_order_qty > 0 ? (
                        <span className="reorder-chip">
                          +<strong>{item.suggested_order_qty}</strong> pcs (ROP: {item.reorder_point})
                        </span>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="button button-quiet"
                        onClick={() => pick(item.sku)}
                      >
                        {isSelected ? "Calculating" : "Analyze EOQ"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {filteredItems.length > visible ? (
          <div className="sk-more"><span>Showing {visible} of {filteredItems.length} SKUs</span><div><button type="button" className="button button-secondary" onClick={() => setVisible((v) => v + PAGE)}>Show {Math.min(PAGE, filteredItems.length - visible)} more</button><button type="button" className="sk-link-button" onClick={() => setVisible(filteredItems.length)}>Show all</button></div></div>
        ) : filteredItems.length > 0 ? <p className="sk-more-note">All {filteredItems.length} SKUs shown</p> : null}
      </Card>

      {/* Interactive EOQ Optimization Calculator */}
      <div ref={lab} className="inventory-lab-anchor" />
      {activeItem && eoqCalculation && (
        <Card className="tier-panel sk-panel sk-rise" key={activeItem.sku}>
          <div className="panel-heading sk-panel-heading">
            <div>
              <span className="eyebrow">INTERACTIVE DECISION LAB</span>
              <h2>Economic Order Quantity (EOQ) Optimizer: {activeItem.sku}</h2>
            </div>
            <span className="placeholder-tag">DETERMINISTIC FORMULA</span>
          </div>

          <div className="eoq-grid">
            <div className="eoq-controls">
              <label className="slider-group">
                <div className="slider-label">
                  <span>Ordering / PO Setup Cost</span>
                  <strong>PKR {setupCost.toLocaleString()}</strong>
                </div>
                <input
                  type="range"
                  min="500"
                  max="15000"
                  step="500"
                  value={setupCost}
                  onChange={(e) => setSetupCost(Number(e.target.value))}
                />
                <small className="footnote">Staff time, paperwork, vendor freight fees per batch</small>
              </label>

              <label className="slider-group">
                <div className="slider-label">
                  <span>Annual Holding Cost Rate</span>
                  <strong>{holdingRate}% / year</strong>
                </div>
                <input
                  type="range"
                  min="5"
                  max="40"
                  step="1"
                  value={holdingRate}
                  onChange={(e) => setHoldingRate(Number(e.target.value))}
                />
                <small className="footnote">Warehousing, working capital cost of funds, shrinkage</small>
              </label>

              <div className="item-quick-facts">
                <div>
                  <span className="eyebrow">Current Unit Cost</span>
                  <strong><MoneyText amountMinor={activeItem.unit_cost_minor} /></strong>
                </div>
                <div>
                  <span className="eyebrow">Annualised Demand</span>
                  <strong>{eoqCalculation.annualDemand} units</strong>
                </div>
                <div>
                  <span className="eyebrow">Lead Time</span>
                  <strong>{activeItem.lead_time_days} days</strong>
                </div>
              </div>
            </div>

            <div className="eoq-results">
              <div className="eoq-result-card">
                <span className="eyebrow">OPTIMAL BATCH SIZE (EOQ)</span>
                <span className="eoq-highlight-number">{eoqCalculation.eoq} units</span>
                <p>Order {eoqCalculation.eoq} pieces every ~{(365 / Number(eoqCalculation.ordersPerYear)).toFixed(0)} days to minimize combined inventory holding and purchasing costs.</p>
              </div>

              <div className="eoq-cost-breakdown">
                <div>
                  <span>Target Orders / Year</span>
                  <strong>{eoqCalculation.ordersPerYear} orders</strong>
                </div>
                <div>
                  <span>Safety Stock Buffer</span>
                  <strong>{activeItem.safety_stock} units</strong>
                </div>
                <div>
                  <span>Reorder Point (ROP)</span>
                  <strong>{activeItem.reorder_point} units</strong>
                </div>
                <div className="total-annual-cost">
                  <span>Est. Annual Logistics Cost</span>
                  <strong>PKR {Math.round(eoqCalculation.totalCost).toLocaleString()}</strong>
                </div>
              </div>
            </div>
          </div>
          <p className="proposal-reasoning">
            Guardian G-02 verification: Reorder proposals generated through this model are constrained by the business’s 13-week cash buffer. Automatic purchase order creation remains blocked until authorized by the owner.
          </p>
        </Card>
      )}
    </div>
  );
}
