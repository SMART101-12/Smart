# SMART Iterative Model Research Protocol

## Purpose
این پروتکل به موتور اجازه می‌دهد چرخه آزمایش را تا رسیدن به یک مدل قابل اتکا ادامه دهد؛ اما «قابل اتکا» با یک معیار از پیش تعیین‌شده و قابل سنجش تعریف می‌شود، نه با رسیدن اجباری به 99%.

## Promotion Gates
یک Candidate فقط وقتی Promote می‌شود که همه این موارد را پاس کند:

1. Data validation و calendar validation سبز.
2. Unit/integration tests سبز.
3. بدون look-ahead و leakage در audit.
4. بهتر از Naive در OOS از نظر MAE و/یا معیار معاملاتی با معنی آماری/اقتصادی.
5. Direction Accuracy پایدار در چند پنجره، نه فقط یک پنجره.
6. عملکرد قابل قبول در Bull/Bear/Sideways و volatility regimes.
7. Drawdown و risk limits قابل قبول.
8. confidence calibration قابل قبول.
9. نتیجه در چند seed / parameter perturbation شکننده نباشد.
10. complexity متناسب با improvement باشد.
11. نتیجه قابل بازتولید از Git commit باشد.

## Loop
`Hypothesis -> Build -> Unit Test -> Historical Walk-Forward -> Error Analysis -> Candidate Selection -> Combination -> Re-test -> Frozen OOS -> Promote/Reject -> Memory`

هر مدل Reject شده در حافظه می‌ماند. هر اصلاح باید parent model و دلیل تغییر را ثبت کند.

## Search Strategy
- Stage 1: single indicators
- Stage 2: pairwise
- Stage 3: triples
- Stage 4: small ensembles
- Stage 5: model-of-models
- Stage 6: regime-specific models
- Stage 7: calibrated forecast
- Stage 8: separate Entry/Stop/Target/Exit optimization
- Stage 9: multi-symbol validation

برای جلوگیری از انفجار ترکیب‌ها، ابتدا feature redundancy و correlation/MI و stability ranking انجام می‌شود و سپس pair/triple search روی candidates منتخب انجام می‌گیرد. حذف باید ثبت‌شده باشد.

## Error-driven Learning
پس از هر iteration:
- بزرگ‌ترین خطاها استخراج می‌شوند.
- خطا بر اساس regime، trend، momentum، volume، volatility، breakout، reversal، calendar/data و execution دسته‌بندی می‌شود.
- یک hypothesis برای رفع مهم‌ترین خطا ساخته می‌شود.
- hypothesis در پنجره‌های جدید تست می‌شود.
- اگر فقط training بهتر شد و OOS بهتر نشد، Reject.

## Stop Conditions
چرخه تا بی‌نهایت اجرا نمی‌شود. برای هر generation سقف compute و معیار توقف داریم. اما پروژه تا وقتی Candidate نهایی همه gateها را پاس نکند، «Final Model» اعلام نمی‌کند.

## Final Validation
پس از انتخاب candidate، یک مجموعه OOS کاملاً فریز می‌شود. هیچ tuning بعدی روی آن مجاز نیست. سپس candidate روی چند نماد و بازار/تقویم متناسب validation می‌شود.

## Trading Layer
پیش‌بینی قیمت به‌تنهایی کافی نیست. پس از اثبات forecast:
- Entry trigger
- Entry zone
- Stop/invalidation
- T1/T2/T3
- trailing/breakeven
- Exit
به‌صورت جداگانه و سپس end-to-end تست می‌شوند.

## User-facing result
هر iteration باید خلاصه کند:
- Candidate
- Tests
- OOS metrics
- Baseline comparison
- Main error
- Change made
- Change impact
- Promote/Reject

## Important
هدف «مدل قابل اتکا» است، نه «عدد 99% به هر قیمت». اگر بازار اجازه دقت موردنظر را ندهد، سیستم باید آن را صادقانه گزارش کند.
