# Procurement report

Comparing 4 supplier replies for this RFQ.

## 1. Normalized supplier comparison

### Buyer requirements

- **Part:** BRK-4471-A[^buyer-part]
- **Description:** machined aluminium bracket[^buyer-description]
- **Quantity:** 60000[^buyer-quantity]
- **Quantity basis:** annual[^buyer-quantity_basis]
- **Revision:** Unknown / not stated
- **Material finish:** Unknown / not stated
- **Destination:** Unknown / not stated
- **Release schedule:** Unknown / not stated
- **Required delivery:** Unknown / not stated
- **Priorities:** Unknown / not stated

### Supplier terms

Price extensions are arithmetic scenarios, not confirmed ordering plans or landed costs. Unknown charges are not zero. No FX conversion, automatic discount, index adjustment, or tooling-amortization saving is applied. Contextual currency assumptions are labelled inferred and require confirmation.

| Field | Tri-State Metalcraft | Nordkant Prazisionsteile GmbH | Pacific Rim Components | Brightwater Precision |
| --- | --- | --- | --- | --- |
| Supplier / source | Tri-State Metalcraft[^supplier_1-supplier] | Nordkant Prazisionsteile GmbH[^supplier_2-supplier] | Pacific Rim Components[^supplier_3-supplier] | Brightwater Precision[^supplier_4-supplier] |
| Part | BRK-4471-A[^supplier_1-part] | BRK-4471-A[^supplier_2-part] | BRK-4471-A[^supplier_3-part] | BRK-4471-A[^supplier_4-part] |
| Drawing revision | Unknown / not stated | rev C[^supplier_2-revision] | REV B[^supplier_3-revision] | Unknown / not stated |
| Material / finish statements | anodizing[^supplier_1-material_finish] | Unknown / not stated | anodizing subcontracted[^supplier_3-material_finish] | Unknown / not stated |
| Original quoted price | 4.85[^supplier_1-quoted_price] | 3.92[^supplier_2-quoted_price] | 3240[^supplier_3-quoted_price] | 4.40[^supplier_4-quoted_price] |
| Pieces per quoted price | 1[^supplier_1-price_basis_quantity] | 1[^supplier_2-price_basis_quantity] | 1000[^supplier_3-price_basis_quantity] | 1[^supplier_4-price_basis_quantity] |
| Price currency | USD (inferred; quoted $)[^supplier_1-currency] | EUR (explicit)[^supplier_2-currency] | USD (explicit)[^supplier_3-currency] | USD (inferred; quoted $)[^supplier_4-currency] |
| Price qualifications | at your 60k annual number -- we'd hold that price for releases of 5,000 or more, below that we'd have to look at it again[^supplier_1-price_qualification] | annual volume[^supplier_2-price_qualification] | PRICE BASED ON DRAWING REV B[^supplier_3-price_qualification] | at your volumes[^supplier_4-price_qualification] |
| Selected annual volume tier | 60000[^supplier_1-annual_volume] | 60000[^supplier_2-annual_volume] | Unknown / not stated | Unknown / not stated |
| MOQ | Unknown / not stated | Unknown / not stated | 25000[^supplier_3-moq] | Unknown / not stated |
| Minimum release | 5000[^supplier_1-min_release] | Unknown / not stated | Unknown / not stated | Unknown / not stated |
| Stated tooling amount | 6200[^supplier_1-tooling_amount] | Unknown / not stated | 4800[^supplier_3-tooling_amount] | Unknown / not stated |
| Tooling currency | USD (inferred; quoted $)[^supplier_1-tooling_currency] | Unknown / not stated | USD (explicit)[^supplier_3-tooling_currency] | Unknown / not stated |
| Tooling terms | one time, invoiced on PO[^supplier_1-tooling_terms] | included, amortized over first 40,000 pcs[^supplier_2-tooling_terms] | Unknown / not stated | Tooling we'd need to confirm after our engineering team reviews the drawing -- I don't want to quote you a number and then change it.[^supplier_4-tooling_terms] |
| Container / packaging deposit | Unknown / not stated | 2800[^supplier_2-deposit_amount] | Unknown / not stated | Unknown / not stated |
| Deposit currency | Unknown / not stated | EUR[^supplier_2-deposit_currency] | Unknown / not stated | Unknown / not stated |
| Deposit conditions | Unknown / not stated | refundable[^supplier_2-deposit_terms] | Unknown / not stated | Unknown / not stated |
| Delivery / cost coverage | FOB our dock in Cleveland[^supplier_1-delivery_terms] | DDP Columbus, Ohio[^supplier_2-delivery_terms] | FOB KAOHSIUNG[^supplier_3-delivery_terms] | EXW Queretaro[^supplier_4-delivery_terms] |
| Lead time / starting condition | 4 weeks from release, and we can usually beat that[^supplier_1-lead_time] | 11 weeks from order release[^supplier_2-lead_time] | 9 WEEKS PRODUCTION[^supplier_3-lead_time] | 6-8 weeks once we're running[^supplier_4-lead_time] |
| Payment | Net 30[^supplier_1-payment_terms] | Net 60 days. 2% discount for payment within 10 days.[^supplier_2-payment_terms] | 30% T/T DEPOSIT, 70% BEFORE SHIPMENT[^supplier_3-payment_terms] | Unknown / not stated |
| Price validity | Pricing firm for 90 days[^supplier_1-validity] | 30 days from date of issue[^supplier_2-validity] | Unknown / not stated | Unknown / not stated |
| Price adjustment | Unknown / not stated | Prices subject to quarterly adjustment per LME aluminium index, base 2026 Q1. Adjustments applied where index moves more than 4%.[^supplier_2-price_adjustment] | Unknown / not stated | Unknown / not stated |
| Other terms | Anodizing is done in house so we're not exposed on that the way some of the overseas guys are.[^supplier_1-other_terms] | Packaging: returnable steel containers[^supplier_2-other_terms] | SHIPPING 5 WEEKS OCEAN; FREIGHT AND DUTY NOT INCLUDED[^supplier_3-other_terms] | we'd carry four weeks of safety stock for you at our facility at no charge[^supplier_4-other_terms] |
| Currency basis | USD inferred from the bare $ symbol and explicit USD pricing in this RFQ; supplier confirmation required. | Explicitly stated in the quote. | Explicitly stated in the quote. | USD inferred from the bare $ symbol and explicit USD pricing in this RFQ; supplier confirmation required. |
| Delivery-cost coverage | Nominal FOB price; full delivered cost is not established. Confirm freight and duty coverage. | DDP to the quoted location; confirm that it matches the buyer destination. No cross-currency landed-cost ranking. | Nominal unit price only: freight and duty excluded. No confirmed landed-cost advantage over delivered offers. | Nominal ex-works price; transport and import costs are not established. |
| Nominal unit price / piece (not landed cost) | USD 4.85 (inferred currency) | EUR 3.92 | USD 3.24 | USD 4.40 (inferred currency) |
| Annual price extension (conditional) | USD 291,000.00 (inferred currency) | EUR 235,200.00 | USD 194,400.00 | USD 264,000.00 (inferred currency) |
| Extension + one stated tooling charge (conditional) | USD 297,200.00 (inferred currency) | Unknown / not calculated | USD 199,200.00 | Unknown / not calculated |


Calculated rows use the cited original price, price basis, buyer quantity, and stated tooling. Deposits remain separate. Unit prices are displayed to at most six decimal places; extensions to two, using decimal half-even rounding. Approximate quotes remain indicative.

### Source evidence

[^buyer-part]: We need a machined aluminium bracket, part BRK-4471-A, 60,000 units a year.
[^buyer-description]: We need a machined aluminium bracket, part BRK-4471-A, 60,000 units a year.
[^buyer-quantity]: We need a machined aluminium bracket, part BRK-4471-A, 60,000 units a year.
[^buyer-quantity_basis]: We need a machined aluminium bracket, part BRK-4471-A, 60,000 units a year.
[^supplier_1-supplier]: Quote 1 — Tri-State Metalcraft
[^supplier_2-supplier]: NORDKANT PRAZISIONSTEILE GMBH
[^supplier_3-supplier]: Quote 3 — Pacific Rim Components
[^supplier_4-supplier]: Quote 4 — Brightwater Precision
[^supplier_1-part]: Subject: RE: RFQ BRK-4471-A
[^supplier_2-part]: Part: BRK-4471-A (per customer drawing rev C)
[^supplier_3-part]: PART NO BRK-4471-A
[^supplier_4-part]: Subject: BRK-4471-A
[^supplier_2-revision]: Part: BRK-4471-A (per customer drawing rev C)
[^supplier_3-revision]: NOTES PRICE BASED ON DRAWING REV B
[^supplier_1-material_finish]: Pricing firm for 90 days. Anodizing is done in house so we're not exposed
[^supplier_3-material_finish]: ANODIZING SUBCONTRACTED
[^supplier_1-quoted_price]: $4.85 per piece, FOB our dock in Cleveland. That's at your 60k annual
[^supplier_2-quoted_price]: 60,000 pcs EUR 3.92 / pc
[^supplier_3-quoted_price]: UNIT PRICE USD 3,240.00 / 1,000 PCS
[^supplier_4-quoted_price]: We can do this part. Looking at around $4.40 a piece at your volumes,
[^supplier_1-price_basis_quantity]: $4.85 per piece, FOB our dock in Cleveland. That's at your 60k annual
[^supplier_2-price_basis_quantity]: 60,000 pcs EUR 3.92 / pc
[^supplier_3-price_basis_quantity]: UNIT PRICE USD 3,240.00 / 1,000 PCS
[^supplier_4-price_basis_quantity]: We can do this part. Looking at around $4.40 a piece at your volumes,
[^supplier_1-currency]: $4.85 per piece, FOB our dock in Cleveland. That's at your 60k annual
[^supplier_2-currency]: 60,000 pcs EUR 3.92 / pc
[^supplier_3-currency]: UNIT PRICE USD 3,240.00 / 1,000 PCS
[^supplier_4-currency]: We can do this part. Looking at around $4.40 a piece at your volumes,
[^supplier_1-price_qualification]: $4.85 per piece, FOB our dock in Cleveland. That's at your 60k annual number -- we'd hold that price for releases of 5,000 or more, below that we'd have to look at it again.
[^supplier_2-price_qualification]: Price schedule, annual volume:
[^supplier_3-price_qualification]: NOTES PRICE BASED ON DRAWING REV B
[^supplier_4-price_qualification]: We can do this part. Looking at around $4.40 a piece at your volumes,
[^supplier_1-annual_volume]: $4.85 per piece, FOB our dock in Cleveland. That's at your 60k annual
[^supplier_2-annual_volume]: 60,000 pcs EUR 3.92 / pc
[^supplier_3-moq]: MOQ 25,000 PCS
[^supplier_1-min_release]: number -- we'd hold that price for releases of 5,000 or more, below that
[^supplier_1-tooling_amount]: Tooling is $6,200, one time, invoiced on PO.
[^supplier_3-tooling_amount]: TOOLING USD 4,800.00
[^supplier_1-tooling_currency]: Tooling is $6,200, one time, invoiced on PO.
[^supplier_3-tooling_currency]: TOOLING USD 4,800.00
[^supplier_1-tooling_terms]: Tooling is $6,200, one time, invoiced on PO.
[^supplier_2-tooling_terms]: Tooling: included, amortized over first 40,000 pcs
[^supplier_4-tooling_terms]: Tooling we'd need to confirm after our engineering team reviews the drawing -- I don't want to quote you a number and then change it.
[^supplier_2-deposit_amount]: Packaging: returnable steel containers, deposit EUR 2,800 (refundable)
[^supplier_2-deposit_currency]: Packaging: returnable steel containers, deposit EUR 2,800 (refundable)
[^supplier_2-deposit_terms]: Packaging: returnable steel containers, deposit EUR 2,800 (refundable)
[^supplier_1-delivery_terms]: $4.85 per piece, FOB our dock in Cleveland. That's at your 60k annual
[^supplier_2-delivery_terms]: Delivery: DDP Columbus, Ohio
[^supplier_3-delivery_terms]: TERMS FOB KAOHSIUNG
[^supplier_4-delivery_terms]: EXW Queretaro. Lead time 6-8 weeks once we're running.
[^supplier_1-lead_time]: Lead time 4 weeks from release, and we can usually beat that. Net 30.
[^supplier_2-lead_time]: Lead time: 11 weeks from order release
[^supplier_3-lead_time]: LEAD TIME 9 WEEKS PRODUCTION
[^supplier_4-lead_time]: EXW Queretaro. Lead time 6-8 weeks once we're running.
[^supplier_1-payment_terms]: Lead time 4 weeks from release, and we can usually beat that. Net 30.
[^supplier_2-payment_terms]: Payment: Net 60 days. 2% discount for payment within 10 days.
[^supplier_3-payment_terms]: PAYMENT 30% T/T DEPOSIT, 70% BEFORE SHIPMENT
[^supplier_1-validity]: Pricing firm for 90 days. Anodizing is done in house so we're not exposed
[^supplier_2-validity]: Validity: 30 days from date of issue.
[^supplier_2-price_adjustment]: Prices subject to quarterly adjustment per LME aluminium index, base 2026 Q1. Adjustments applied where index moves more than 4%.
[^supplier_1-other_terms]: Pricing firm for 90 days. Anodizing is done in house so we're not exposed on that the way some of the overseas guys are.
[^supplier_2-other_terms]: Packaging: returnable steel containers, deposit EUR 2,800 (refundable)
[^supplier_3-other_terms]: SHIPPING 5 WEEKS OCEAN TOOLING USD 4,800.00 PAYMENT 30% T/T DEPOSIT, 70% BEFORE SHIPMENT NOTES PRICE BASED ON DRAWING REV B ANODIZING SUBCONTRACTED FREIGHT AND DUTY NOT INCLUDED
[^supplier_4-other_terms]: One thing worth mentioning: we'd carry four weeks of safety stock for you at our facility at no charge, which I know has been an issue for you

## 2. Risks / unknowns

- **Before final comparison — Required drawing revision:** Nordkant Prazisionsteile GmbH references drawing revision C; Pacific Rim Components references drawing revision B. The buyer's required drawing revision is not provided; confirm it before assessing compliance.
- **Before final comparison — Buyer destination:** Buyer destination is missing. Supplier delivery locations are quote terms, not buyer requirements; delivered-cost comparison needs the actual destination.
- **Before final comparison — Release schedule:** Buyer release schedule is missing. Annual demand does not establish order sizes or release frequency; quoted volume and minimum-quantity conditions cannot yet be checked against the purchasing plan.
- **Cost comparison — Pacific Rim Components:** Nominal unit price only: freight and duty excluded. No confirmed landed-cost advantage over delivered offers.
- The buyer's required drawing revision is unknown, which prevents confirmation of technical compliance for all suppliers. This must be resolved before a final award. (Sources: Buyer, Nordkant Prazisionsteile GmbH, Pacific Rim Components)
- Buyer destination is missing, so delivered-cost comparison and logistics arrangements cannot be finalized until the actual destination is confirmed. (Sources: Buyer, Tri-State Metalcraft, Nordkant Prazisionsteile GmbH, Pacific Rim Components, Brightwater Precision)
- Buyer release schedule is missing, so supplier minimum order and release conditions cannot be checked against the purchasing plan. (Sources: Buyer, Tri-State Metalcraft, Nordkant Prazisionsteile GmbH, Pacific Rim Components)

### Prioritized supplier issues

| Severity / category | Supplier | Unresolved issue | Evidence |
| --- | --- | --- | --- |
| **HIGH** / cost | Tri-State Metalcraft | The quoted scope does not establish delivered cost; obtain the remaining logistics costs after buyer destination confirmation. | Delivery / cost coverage[^supplier_1-delivery_terms]; Other terms[^supplier_1-other_terms] |
| **MEDIUM** / cost | Tri-State Metalcraft | Currency or pricing qualification needs confirmation; conditional shortlisting remains possible. | Price currency[^supplier_1-currency]; Original quoted price[^supplier_1-quoted_price] |
| **MEDIUM** / cost | Tri-State Metalcraft | Currency or pricing qualification needs confirmation; conditional shortlisting remains possible. | Tooling currency[^supplier_1-tooling_currency]; Stated tooling amount[^supplier_1-tooling_amount] |
| **HIGH** / technical | Nordkant Prazisionsteile GmbH | Quoted revision bases differ. After the buyer establishes the required revision, this supplier must confirm compliance or re-quote. | Drawing revision[^supplier_2-revision]; Pacific Rim Components / Drawing revision[^supplier_3-revision] |
| **HIGH** / technical | Pacific Rim Components | Quoted revision bases differ. After the buyer establishes the required revision, this supplier must confirm compliance or re-quote. | Drawing revision[^supplier_3-revision]; Nordkant Prazisionsteile GmbH / Drawing revision[^supplier_2-revision] |
| **HIGH** / cost | Pacific Rim Components | The quoted scope does not establish delivered cost; obtain the remaining logistics costs after buyer destination confirmation. | Delivery / cost coverage[^supplier_3-delivery_terms]; Other terms[^supplier_3-other_terms] |
| **HIGH** / delivery | Pacific Rim Components | The quoted duration has a production, startup or approval condition; full delivery timing needs clarification. | Lead time / starting condition[^supplier_3-lead_time] |
| **HIGH** / cost | Brightwater Precision | The price is provisional; a firm price and its conditions are unresolved. | Price qualifications[^supplier_4-price_qualification]; Original quoted price[^supplier_4-quoted_price] |
| **HIGH** / cost | Brightwater Precision | Tooling is explicitly pending; its cost must be established before firm cost comparison. | Stated tooling amount: Not established; Tooling terms[^supplier_4-tooling_terms] |
| **HIGH** / cost | Brightwater Precision | The quoted scope does not establish delivered cost; obtain the remaining logistics costs after buyer destination confirmation. | Delivery / cost coverage[^supplier_4-delivery_terms]; Other terms[^supplier_4-other_terms] |
| **HIGH** / delivery | Brightwater Precision | The quoted duration has a production, startup or approval condition; full delivery timing needs clarification. | Lead time / starting condition[^supplier_4-lead_time] |
| **MEDIUM** / cost | Brightwater Precision | Currency or pricing qualification needs confirmation; conditional shortlisting remains possible. | Price currency[^supplier_4-currency]; Original quoted price[^supplier_4-quoted_price] |

## 3. Shortlist / recommendation

Advance means pursue clarification or a firm offer, not approve a purchase. Shared buyer unknowns can prevent a final comparison while allowing conditional shortlisting. Hold identifies a material clarification need; do not advance identifies a supplier-specific blocker.

| Supplier | Action | Reason / next step |
| --- | --- | --- |
| Tri-State Metalcraft | **Shortlist / advance with clarification** | Tri-State Metalcraft provides a clear price and tooling quote, but the currency is inferred and not confirmed, and the quoted price is FOB Cleveland, so delivered cost is not established. These are not blockers for shortlisting, but require clarification. The buyer's required revision, destination, and release schedule must also be confirmed. Clarifications: The quoted scope does not establish delivered cost; obtain the remaining logistics costs after buyer destination confirmation. Currency or pricing qualification needs confirmation; conditional shortlisting remains possible. Currency or pricing qualification needs confirmation; conditional shortlisting remains possible. Nordkant Prazisionsteile GmbH references drawing revision C; Pacific Rim Components references drawing revision B. The buyer's required drawing revision is not provided; confirm it before assessing compliance. Buyer destination is missing. Supplier delivery locations are quote terms, not buyer requirements; delivered-cost comparison needs the actual destination. Buyer release schedule is missing. Annual demand does not establish order sizes or release frequency; quoted volume and minimum-quantity conditions cannot yet be checked against the purchasing plan. |
| Nordkant Prazisionsteile GmbH | **Shortlist / advance with clarification** | Nordkant Prazisionsteile GmbH quotes Rev C and DDP Columbus, Ohio, with tooling amortized in the piece price. The revision quoted may not match the buyer's requirement, so confirmation is needed after the buyer states the required revision. The buyer's destination and release schedule must also be confirmed. Nordkant Prazisionsteile GmbH quotes Rev C; Pacific Rim Components references Rev B. The buyer's required revision is unknown. Technical equivalence is unconfirmed pending buyer confirmation; neither supplier's quoted revision establishes the requirement. Clarifications: Quoted revision bases differ. After the buyer establishes the required revision, this supplier must confirm compliance or re-quote. Nordkant Prazisionsteile GmbH references drawing revision C; Pacific Rim Components references drawing revision B. The buyer's required drawing revision is not provided; confirm it before assessing compliance. Buyer destination is missing. Supplier delivery locations are quote terms, not buyer requirements; delivered-cost comparison needs the actual destination. Buyer release schedule is missing. Annual demand does not establish order sizes or release frequency; quoted volume and minimum-quantity conditions cannot yet be checked against the purchasing plan. |
| Pacific Rim Components | **Shortlist / advance with clarification** | Pacific Rim Components quotes Rev B, FOB Kaohsiung, with explicit tooling and a minimum order quantity. The quoted revision may not match the buyer's requirement, and delivered cost is not established. Lead time is quoted for production only, not including shipping. These issues require clarification, as does the buyer's revision, destination, and release schedule. Pacific Rim Components quotes Rev B; Nordkant Prazisionsteile GmbH references Rev C. The buyer's required revision is unknown. Technical equivalence is unconfirmed pending buyer confirmation; neither supplier's quoted revision establishes the requirement. Clarifications: Quoted revision bases differ. After the buyer establishes the required revision, this supplier must confirm compliance or re-quote. The quoted scope does not establish delivered cost; obtain the remaining logistics costs after buyer destination confirmation. The quoted duration has a production, startup or approval condition; full delivery timing needs clarification. Nordkant Prazisionsteile GmbH references drawing revision C; Pacific Rim Components references drawing revision B. The buyer's required drawing revision is not provided; confirm it before assessing compliance. Buyer destination is missing. Supplier delivery locations are quote terms, not buyer requirements; delivered-cost comparison needs the actual destination. Buyer release schedule is missing. Annual demand does not establish order sizes or release frequency; quoted volume and minimum-quantity conditions cannot yet be checked against the purchasing plan. |
| Brightwater Precision | **Shortlist / advance with clarification** | Brightwater Precision provides a provisional price, but tooling cost is not quoted and the price is not firm. The currency is inferred but not confirmed, and the quote is EXW Queretaro, so delivered cost is not established. Lead time is also conditional. These are material issues that must be clarified, along with the buyer's revision, destination, and release schedule. Clarifications: The price is provisional; a firm price and its conditions are unresolved. Tooling is explicitly pending; its cost must be established before firm cost comparison. The quoted scope does not establish delivered cost; obtain the remaining logistics costs after buyer destination confirmation. Nordkant Prazisionsteile GmbH references drawing revision C; Pacific Rim Components references drawing revision B. The buyer's required drawing revision is not provided; confirm it before assessing compliance. Buyer destination is missing. Supplier delivery locations are quote terms, not buyer requirements; delivered-cost comparison needs the actual destination. Buyer release schedule is missing. Annual demand does not establish order sizes or release frequency; quoted volume and minimum-quantity conditions cannot yet be checked against the purchasing plan. |

## 4. Follow-up questions

Drafts only; no messages have been sent.

### Buyer

**Resolve first — BLOCKER — buyer requirements for final comparison:**

- Please confirm the required drawing revision for BRK-4471-A so that supplier compliance can be assessed. (Sources: Buyer, Nordkant Prazisionsteile GmbH, Pacific Rim Components)
- Please confirm the delivery destination for this part so that delivered-cost comparisons can be completed. (Sources: Buyer, Tri-State Metalcraft, Nordkant Prazisionsteile GmbH, Pacific Rim Components, Brightwater Precision)
- Please confirm your intended release schedule (order sizes and frequency) for this part so that supplier minimum order and release conditions can be checked. (Sources: Buyer, Tri-State Metalcraft, Nordkant Prazisionsteile GmbH, Pacific Rim Components)


### Tri-State Metalcraft

**HIGH — Commercial clarification:**

- Please provide an estimate of freight and duty costs to the buyer's destination once confirmed, to establish the full delivered cost. Also, confirm the currency for your quoted unit price and tooling charge. (Sources: Tri-State Metalcraft)


### Nordkant Prazisionsteile GmbH

**HIGH — Commercial clarification:**

- Once the buyer confirms the required drawing revision, please confirm whether your quote is fully compliant or if a re-quote is needed. (Sources: Nordkant Prazisionsteile GmbH)


### Pacific Rim Components

**HIGH — Commercial clarification:**

- Once the buyer confirms the required drawing revision, please confirm whether your quote is fully compliant or if a re-quote is needed. Also, please provide an estimate of freight and duty costs to the buyer's destination once confirmed, and clarify the total lead time from order to delivery at the buyer's destination, including production, shipping, and any approval or startup conditions. (Sources: Pacific Rim Components)


### Brightwater Precision

**HIGH — Commercial clarification:**

- Please confirm a firm unit price and its conditions, including any volume or release requirements. Also, provide a firm tooling cost and terms after your engineering review, and an estimate of freight and duty costs to the buyer's destination once confirmed. (Sources: Brightwater Precision)


Confirm assumptions, technical compliance and unresolved costs against the original quotes before a purchasing decision.
