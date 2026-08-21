# Report Spec

## Report identity
- Report name: Presight Project Spend Performance
- Semantic model: Presight Spend Analytics
- Audience: Finance and Operations executives
- Primary purpose: Show whether the project portfolio is on plan, where overruns are concentrated, and how transaction spend is trending.
- Delivery target: Local PBIP project and final `outputs/results/sanjay_subair/02_sql_and_viz/presight_dashboard.pbix`

## User decisions and constraints
- Scope: One-page executive dashboard.
- Page count: 1.
- Interactivity: Region, project status, and year slicers; predictable cross-filtering.
- Design direction: Modern, sleek Corporate Cool design with SVG iconography and no third-party custom visual dependency.
- Publishing: Local only.
- Tooling: Power BI Desktop is available; Power BI modeling MCP is available; Node.js is available.
- Model edit permissions: Create a new local import semantic model from the cleaned CSV outputs.
- Accessibility: WCAG AA contrast, insight-led alt text, logical tab order, non-color status cues.
- Data caveats: Project `actual_cost` is the portfolio actual-spend KPI. Transaction `amount_aed` drives the monthly trend and vendor concentration visuals. These fields represent different business grains and must not be presented as reconciled totals.

## Narrative
- Core story: The portfolio is 14.1% below its total allocated budget, but 29.0% of projects are individually over budget.
- Audience promise: An executive can identify overall status, department pressure, trend direction, vendor concentration, and the largest project overruns in under ten seconds.
- Key questions answered:
  - What are total budget, actual project cost, over-budget rate, and transaction volume?
  - Which departments carry the most budget and actual cost?
  - How does monthly transaction spend change across the leading categories?
  - Which vendors account for the greatest share of transaction spend?
  - Which ten projects have the largest adverse budget variance?

## Design identity
- Tone: Corporate Cool — cool-grey surface, slate typography, cyan/blue emphasis, disciplined spacing, and restrained semantic alert colors.
- Signature: Every KPI card uses a compact cyan/blue-accented SVG line icon with a flush accent edge, large tabular-looking value, and concise context label.
- Brownfield delta: Not applicable; this is a greenfield report.

## Page plan
1. Portfolio spend remains below plan while project-level overruns persist
   - Archetype: Executive Summary
   - Layout variant: B — KPI Strip
   - Variant rationale: Four equally important KPIs and five mandatory analytical visuals require a balanced full-width KPI strip rather than a single oversized hero.
   - Purpose: Provide an executive scan of portfolio status, trend, concentration, and exceptions.
   - Visuals: Four KPI cards, clustered department bar chart, category line chart, vendor donut, top-project table, and three slicers.
   - Fields/measures: Budget, actual cost, over-budget project rate, transaction count, department, transaction date, category, vendor group, project, and budget variance.
   - Slicers/interactions: Region, project status, and year filter all applicable measures. The year slicer uses transaction year directly and applies to project measures through project start year.

## Design system summary
- Theme name + base palette: `Presight Corporate Cool`; surface `#F1F5F9`, white containers, slate `#0F172A`, cyan `#06B6D4`, blue `#2563EB`, amber `#D97706`, red `#DC2626`.
- Color semantics: Blue represents budget, cyan represents actual/transaction spend, red represents adverse over-budget status, violet represents transaction volume, and grey represents context or Other.
- Typography pairing: Segoe UI Semibold for titles and Segoe UI for body; Consolas fallback for aligned KPI and table numerals.
- Layout pattern: FHD 12-column grid, 32px margins, 24px gutters, compact two-row KPI strip, three-panel analysis row, and full-width detail table.
- Accessibility commitments: Minimum AA contrast, labeled values in addition to color, descriptive titles, dynamic alt-text measures, and reading order from title to slicers, KPIs, charts, then table.

## Model requirements
- Existing measures: None; greenfield model.
- New measures:
  - Total Budget
  - Total Actual Spend
  - Budget Variance
  - Budget Utilisation %
  - Project Count
  - Over Budget Projects
  - Over Budget Projects %
  - Total Transactions
  - Transaction Spend
  - Vendor Share %
  - Dashboard Headline
  - Dashboard Subtitle
  - Alt Text - Department Spend
  - Alt Text - Monthly Spend
  - Alt Text - Vendor Concentration
  - Alt Text - Project Variance
- New calculated/helper columns:
  - Projects[Start Year]
  - Transactions[Transaction Year]
  - Transactions[Transaction Month Start]
  - Vendors[Vendor Group] with overall top five vendors and `Other`
  - Categories[Category Rank] for a top-five visual filter
- Relationship/sort requirements:
  - Projects[project_id] 1:* Transactions[project_id], active, single direction.
  - Date[Date] 1:* Transactions[transaction_date], active, single direction.
  - Vendors[vendor_name] 1:* Transactions[vendor_name], active, single direction.
  - Categories[category] 1:* Transactions[category], active, single direction.
  - Date[Year] drives project measures through `TREATAS` to Projects[Start Year].
  - Date month labels sort by Date[Month Start].
- Source tables:
  - `outputs/results/sanjay_subair/02_sql_and_viz/projects_clean.csv`
  - `outputs/results/sanjay_subair/02_sql_and_viz/transactions_clean.csv`
  - `outputs/results/sanjay_subair/02_sql_and_viz/employees_clean.csv` retained as a hidden source table for lineage, although it is not required by the executive page.

## Canonical design contract

```yaml
Design Brief:
  generated_by: powerbi-report-design
  contract_version: 1
  mode: greenfield
  design_identity:
    tone: "Corporate Cool — cool-grey surface, slate typography, cyan/blue emphasis, disciplined spacing, restrained semantic alerts"
    signature: "Each KPI card carries a compact cyan/blue-accented SVG line icon, flush accent edge, tabular-looking value, and concise context label."
  archetype: Executive
  color_map:
    - measure: "Projects[Total Budget]"
      color: "#2563EB"
      tint: "#DBEAFE"
    - measure: "Projects[Total Actual Spend]"
      color: "#06B6D4"
      tint: "#CFFAFE"
    - measure: "Projects[Over Budget Projects %]"
      color: "#DC2626"
      tint: "#FEE2E2"
    - measure: "Transactions[Total Transactions]"
      color: "#7C3AED"
      tint: "#EDE9FE"
    - measure: "Transactions[Transaction Spend]"
      color: "#06B6D4"
      tint: "#CFFAFE"
    - measure: "Projects[Budget Variance]"
      color: "#DC2626"
      tint: "#FEE2E2"
  pages:
    - name: "Portfolio spend remains below plan while project-level overruns persist"
      role: landing
      archetype: Executive
      layout_variant: B
      variant_rationale: "Four equally important KPIs plus the five mandatory analytical visuals call for a balanced KPI strip and a dense but readable evidence layout."
      page_background: "#F1F5F9"
      layout_summary: "A wide title and inline filter band lead into four SVG-enhanced KPI cards, three analytical panels, and a full-width ranked exception table."
      layout_contract:
        canvas:
          width: 1920
          height: 1080
          margin: 32
          gutter: 24
          snap: 8
        grid:
          columns: 12
          rows: 12
          regions:
            header: [1, 1, 8, 2]
            filters: [8, 1, 13, 2]
            kpis: [1, 2, 13, 4]
            department_comparison: [1, 4, 5, 9]
            monthly_trend: [5, 4, 10, 9]
            vendor_concentration: [10, 4, 13, 9]
            project_exceptions: [1, 9, 13, 13]
        placements:
          - id: page_title
            region: header
            kind: textbox
            text: "Portfolio spend remains below plan while project-level overruns persist\nSanjay Subair | 20 August 2026"
            purpose: "State the executive finding and satisfy the required author/date attribution."
            field_bindings: "Projects[Dashboard Headline]"
          - id: region_slicer
            region: filters
            kind: slicer
            field_bindings: "Projects[region]"
            slicer_type: dropdown
            slot: 1
            of: 3
          - id: project_status_slicer
            region: filters
            kind: slicer
            field_bindings: "Projects[status]"
            slicer_type: dropdown
            slot: 2
            of: 3
          - id: year_slicer
            region: filters
            kind: slicer
            field_bindings: "Date[Year]"
            slicer_type: dropdown
            slot: 3
            of: 3
          - id: total_budget_card
            region: kpis
            kind: cardVisual
            purpose: "What is the selected portfolio budget?"
            field_bindings: "Projects[Total Budget]"
            color_strategy: measure_match
            comparison_basis: "Selected portfolio scope"
            slot: 1
            of: 4
          - id: total_budget_svg
            region: kpis
            kind: svgImage
            purpose: "Decorative wallet icon that reinforces the budget KPI."
            field_bindings: "resource:svg/wallet.svg"
            color_strategy: measure_match
            decorative_overlay: true
            slot: 1
            of: 4
          - id: actual_spend_card
            region: kpis
            kind: cardVisual
            purpose: "What is selected project actual cost?"
            field_bindings: "Projects[Total Actual Spend]"
            color_strategy: measure_match
            comparison_basis: "Budget utilisation shown in the reference label"
            slot: 2
            of: 4
          - id: actual_spend_svg
            region: kpis
            kind: svgImage
            purpose: "Decorative spend pulse icon that reinforces the actual-cost KPI."
            field_bindings: "resource:svg/spend.svg"
            color_strategy: measure_match
            decorative_overlay: true
            slot: 2
            of: 4
          - id: over_budget_card
            region: kpis
            kind: cardVisual
            purpose: "What share of selected projects is over budget?"
            field_bindings: "Projects[Over Budget Projects %]"
            color_strategy: semantic
            comparison_basis: "Zero-overrun target"
            slot: 3
            of: 4
          - id: over_budget_svg
            region: kpis
            kind: svgImage
            purpose: "Decorative warning triangle that reinforces the over-budget KPI."
            field_bindings: "resource:svg/warning.svg"
            color_strategy: semantic
            decorative_overlay: true
            slot: 3
            of: 4
          - id: transaction_count_card
            region: kpis
            kind: cardVisual
            purpose: "How many transactions are in the selected scope?"
            field_bindings: "Transactions[Total Transactions]"
            color_strategy: measure_match
            comparison_basis: "Filtered transaction population"
            slot: 4
            of: 4
          - id: transaction_count_svg
            region: kpis
            kind: svgImage
            purpose: "Decorative receipt icon that reinforces the transaction-count KPI."
            field_bindings: "resource:svg/receipt.svg"
            color_strategy: measure_match
            decorative_overlay: true
            slot: 4
            of: 4
          - id: department_budget_actual
            region: department_comparison
            kind: clusteredBarChart
            purpose: "Which departments carry the greatest budget and actual project cost?"
            field_bindings:
              Category: "Projects[department]"
              Series:
                - "Projects[Total Budget]"
                - "Projects[Total Actual Spend]"
            sort_policy: value_desc
            color_strategy: measure_match
            comparison_basis: "Actual project cost versus allocated budget"
          - id: monthly_category_spend
            region: monthly_trend
            kind: lineChart
            purpose: "How is monthly transaction spend trending for the five leading categories?"
            field_bindings:
              Category: "Date[Month Start]"
              Legend: "Categories[category]"
              Y: "Transactions[Transaction Spend]"
            visual_filter: "Categories[Category Rank] <= 5"
            sort_policy: natural_order
            color_strategy: unique
          - id: vendor_share
            region: vendor_concentration
            kind: donutChart
            purpose: "How concentrated is transaction spend among the five largest vendors and all other vendors?"
            field_bindings:
              Legend: "Vendors[Vendor Group]"
              Values: "Transactions[Transaction Spend]"
            sort_policy: value_desc
            color_strategy: unique
            design_exception: "The assessment explicitly requires Top 5 plus Other, producing six slices; all slices receive direct percentage labels and Other uses neutral grey."
          - id: top_project_variance
            region: project_exceptions
            kind: tableEx
            purpose: "Which ten projects have the largest adverse budget variance?"
            field_bindings:
              - "Projects[project_name]"
              - "Projects[department]"
              - "Projects[Total Budget]"
              - "Projects[Total Actual Spend]"
              - "Projects[Budget Variance]"
              - "Projects[risk_level]"
            visual_filter: "Top 10 Projects by Projects[Budget Variance]"
            sort_policy: value_desc
            color_strategy: semantic
            comparison_basis: "Actual project cost minus allocated budget"
        space_audit:
          content_cell_count: 132
          placed_cell_count: 132
          empty_cell_pct: 0
          unplaced_regions: []
          largest_region:
            name: project_exceptions
            pct_of_content: 36.4
          balance_rationale: "The mandatory top-ten table receives four rows for legibility; the KPI strip and three evidence panels fill the remaining content area without a dead footer or oversized single-value hero."
  interaction_pattern:
    drill_targets: []
    cross_filter_rules:
      - "Region, project status, and year slicers filter every applicable visual."
      - "Department selection filters the project table and transaction visuals through Projects[project_id]."
      - "Vendor selection highlights the monthly transaction trend and leaves project-only visuals unchanged."
      - "Table row selection does not cross-filter other visuals."
  accessibility:
    alt_text_strategy: "Dynamic headline-and-trend text for KPIs and trend; comparison framing for department, vendor, and project visuals."
    contrast_notes: "Slate text on white or cool-grey surfaces exceeds AA; cyan is not used for body text; red status is paired with labels, percentages, and warning SVG."
    tab_order:
      - page_title
      - region_slicer
      - project_status_slicer
      - year_slicer
      - total_budget_card
      - actual_spend_card
      - over_budget_card
      - transaction_count_card
      - department_budget_actual
      - monthly_category_spend
      - vendor_share
      - top_project_variance
  theme:
    base: "powerbi-report-design/assets/base.json adapted as Presight Corporate Cool"
    user_overrides:
      - "Preserve textbox zero padding and hidden borders."
      - "Preserve card zero padding, compact spacing, white backgrounds, and 8px radius."
      - "Preserve table grow-to-fit, subtle row banding, hidden visual headers, and chart defaults."
      - "Use SVG resources only; do not require marketplace custom visuals."
```

## Implementation notes
- Model changes: Build an Import model from the three cleaned CSV files, add Date, Vendors, and Categories dimensions, and create the listed DAX measures.
- PBIR/report authoring: Generate one FHD page, an adapted theme, four SVG assets, the required visuals, and direct human-readable display names.
- Validation: Validate PBIP structure, JSON, TMDL, measure bindings, sort rules, Top N filters, and slicer behavior.
- Desktop screenshot verification: Open the PBIP in Power BI Desktop, refresh, capture the page, and correct clipping, overlaps, labels, and contrast.
- Publishing boundary: Do not publish to Fabric.
- Risks: The output directory is inside a OneDrive path; all source paths must use robust absolute or parameterized Power Query paths. Power BI Desktop may require the final PBIX save step after the PBIP opens successfully.
