# SMART Learning Memory Protocol

این فایل قرارداد حافظه آزمایش‌های SMART است.

## هر آزمایش باید ذخیره شود
- experiment_id
- timestamp
- symbol
- data_range
- feature_set
- indicator_parameters
- model_version
- training/validation/test ranges
- metrics
- baseline metrics
- complexity
- decision: promote/reject/hold
- reason

## حافظه منفی
مدل باید ترکیب‌های شکست‌خورده را نیز نگه دارد تا در آزمایش بعدی دوباره همان مسیر بی‌دلیل تکرار نشود.

## یادگیری بدون نشت
نتیجه آزمایش فقط پس از پایان پنجره مربوطه وارد حافظه قابل استفاده برای آینده می‌شود. Test set فریز شده تا پایان benchmark نباید وارد tuning شود.

## اصل انتخاب
مدل بهتر مدلی نیست که روی کل گذشته بالاترین امتیاز را دارد؛ مدلی است که در پنجره‌های متعدد و خارج از نمونه، به‌طور پایدار از baseline بهتر باشد و با پیچیدگی کمتر ترجیح داده شود.
