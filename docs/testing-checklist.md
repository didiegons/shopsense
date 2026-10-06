# Assignment 5.4: ShopSense Functional Testing Checklist

Use the local demo catalog and note the input, expected outcome, actual outcome, and pass/fail for each applicable item. Product prices and availability are demo data, not live retailer offers.

## Frontend

- [ ] Brand link returns to the ShopSense home page.
- [ ] Natural-language input accepts an ordinary product request.
- [ ] Submitting a non-empty query with **Interpret requirements** displays the interpreted request without automatically searching products.
- [ ] While interpretation is in progress, the button shows “Interpreting…” and is disabled.
- [ ] Interpretation shows the category, hard constraints, preferences, matched phrases, parser source, confidence, and any clarification.
- [ ] Hard constraints and preferences appear in their respective sections.
- [ ] Edit maximum budget, minimum RAM, maximum weight, or OS after interpretation; confirm edits remain visible.
- [ ] Search products sends the visible structured filter values, not the original natural-language text.
- [ ] With no filters and no unresolved intent, Search products returns the unfiltered demo catalog.
- [ ] A preference-only OS result is not applied to search unless **Apply this OS preference as a hard search filter** is checked.
- [ ] Changing the OS dropdown applies it as a filter.
- [ ] Search button shows “Searching…” and is disabled while the request is in progress.
- [ ] Matching results show brand, model, price, available structured specifications, demo label, availability, and checked date.
- [ ] A result with no structured specifications displays “No structured specifications listed” instead of blank or broken text.
- [ ] Results count matches the returned products.
- [ ] A successful zero-result search shows the no-match message.
- [ ] Search errors appear in an alert and do not leave stale results presented as current results.
- [ ] Submitting a new interpretation clears old results and prior request errors.

## Backend/API

- [ ] `GET /health` returns HTTP 200 and `{"status":"ok"}`.
- [ ] `POST /api/v1/intent` with a normal query returns a validated structured intent and preserves the original query.
- [ ] Intent request with a missing query, whitespace-only query, non-string query, extra field, or query longer than 1,000 characters returns HTTP 422.
- [ ] Budget filter returns no products above the maximum and echoes the applied filter.
- [ ] Minimum RAM filter excludes products with less RAM and products that have no RAM attribute.
- [ ] Maximum weight filter excludes products above the limit and products without a weight attribute.
- [ ] OS family filter `Windows` matches supported Windows versions; explicit `Windows 11` remains version-specific.
- [ ] Combined filters require every supplied hard constraint to match.
- [ ] Category filters, when supplied, match exact product category-attribute key/value pairs.
- [ ] Unknown search request fields are rejected rather than silently ignored.
- [ ] Invalid filter types/ranges return HTTP 422.
- [ ] An impossible but valid filter set returns HTTP 200 with `results: []` and `total: 0`.
- [ ] Products with missing optional laptop specifications serialize without invented values.

## AI Behavior

- [ ] Enter “Laptop under $1000 with at least 16 GB RAM”; verify budget and RAM are extracted as hard constraints.
- [ ] Enter “under 1.5 kg” or “under 1500 grams”; verify the maximum weight is normalized to kilograms.
- [ ] Enter “Windows only” or “must use Windows”; verify Windows family is a hard constraint with no invented version.
- [ ] Enter “I prefer Windows”; verify it is a preference, not a hard constraint.
- [ ] Enter “Windows 11”; verify family and version are distinct and version `11` is retained.
- [ ] Enter a combined cybersecurity/student/virtual-machine request; verify the extracted use-case phrases are sensible and separately visible.
- [ ] Enter “I want a lightweight laptop for school”; verify no numeric weight is invented and a clarification is requested.
- [ ] Enter “Windows or Ubuntu laptop under $1000”; verify clarification is requested and no OS is exposed as an actionable hard constraint.
- [ ] Enter conflicting budget values; verify the parser asks for clarification rather than choosing one silently.
- [ ] With Vertex configured, verify the result says “Vertex AI” and inspect confidence, agreement, and differing fields.
- [ ] With Vertex configuration absent, verify intent extraction uses “Deterministic fallback.”
- [ ] Simulate Vertex authentication, network/model, empty-output, malformed-JSON, or Pydantic-validation failure; verify deterministic fallback is returned.
- [ ] Simulate an unexpected orchestration/programming error; verify it surfaces rather than being silently reported as fallback.
- [ ] For a non-laptop category, verify explicit category entries convert into category hard-constraint/preference maps and do not populate laptop RAM, weight, or OS fields.
- [ ] Verify identical hard-constraint/preference values normalize to the hard constraint; contradictory values are rejected and fallback occurs.
- [ ] Verify arbitrary category attributes remain unregistered/unvalidated by name or unit in this milestone.

## Accessibility

- [ ] Navigate the entire page using Tab and Shift+Tab; focus order follows the visual workflow.
- [ ] Activate Interpret and Search with Enter or Space when focused.
- [ ] Confirm every input and select has an associated visible label.
- [ ] Confirm keyboard focus indicators are visible on links, buttons, inputs, selects, and checkboxes.
- [ ] Confirm interpretation updates are announced through the live region.
- [ ] Confirm search results and empty states are announced through the results live region.
- [ ] Confirm request errors use an alert role and clarification uses a status role.
- [ ] Confirm each product image has descriptive alt text identifying it as a generic demo illustration for that model.
- [ ] Confirm the decorative fallback label does not create confusing duplicate screen-reader output; product name and details remain available as text.
- [ ] Check text zoom and browser zoom at 200% without losing access to controls or results.

## Responsiveness

Test at approximately 320–375 px (small mobile), 390–430 px (mobile), 768 px (tablet), 1024 px (small desktop), and 1440 px (wide desktop).

- [ ] Search filters reflow without horizontal page overflow.
- [ ] Product image and result details stack on narrow screens; image remains visible and does not squeeze price/model text.
- [ ] At tablet and desktop widths, the card image and result details align without overlap.
- [ ] Long model names, specification strings, parser differences, and clarification text wrap without covering adjacent content.
- [ ] Buttons and form controls remain usable and do not clip at small widths.

## Error Handling

- [ ] Submit an empty natural-language query; interpretation cannot be submitted.
- [ ] Submit whitespace-only input; verify no request or useful validation message.
- [ ] Test an overlong query; verify the API validation error is shown.
- [ ] Stop the backend, then try interpretation and search; each displays a clear connection failure and does not crash the page.
- [ ] Return HTTP 422 for intent and search separately; verify the corresponding validation message.
- [ ] Return HTTP 500 or a malformed response; verify the page shows an error and remains usable for retry.
- [ ] Interpret a request requiring clarification, then click Search without confirming; verify search is blocked.
- [ ] Check **Search with only the visible filters** and retry; verify only visible filters are used and unresolved details are not silently applied.
- [ ] Clear that confirmation or enter a new query; verify unresolved confirmation does not carry over unintentionally.
- [ ] Remove the image URL from a test response or return a broken local image path; verify the card shows “Demo image unavailable.”
- [ ] Confirm a failed image does not hide or damage the product title, price, specifications, or availability.

Only the backend test suite and frontend lint/typecheck/build have been automated so far; this checklist describes the manual scenarios to execute for the assignment.
