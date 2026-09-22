# Telegram Profile Rotator — 24/7 بدون روشن بودن کامپیوتر

این پروژه برای این ساخته شده که اکانت شخصی تلگرام را با فاصلهٔ حدود ۱۰ دقیقه، بین چند جفتِ **عکس + @username** بچرخاند.

## نکتهٔ مهم دربارهٔ «همیشه آنلاین»

این نسخه یک برنامهٔ دائمی روی یک VPS نیست. از **GitHub Actions** به‌صورت زمان‌بندی‌شده استفاده می‌کند؛ بنابراین کامپیوترت لازم نیست روشن باشد، ولی اجرای scheduled ممکن است چند دقیقه دیرتر شروع شود. کوتاه‌ترین schedule رسمی GitHub Actions پنج دقیقه است؛ این پروژه هر ۵ دقیقه بررسی می‌کند ولی خودِ چرخش را هر ۱۰ دقیقه انجام می‌دهد.

اجرای standard runner در repository عمومی رایگان است. GitHub همچنین برای workflowهای عمومی امکان schedule و `workflow_dispatch` را فراهم می‌کند.

## 1) ساخت ربات مدیریت

در Telegram برو به `@BotFather` و:

`/newbot`

یک نام و username بده و **BOT TOKEN** را بردار.

این ربات مدیریت است؛ اکانت اصلی تو نیست.

## 2) گرفتن API_ID و API_HASH

برو به:

`https://my.telegram.org`

سپس:

`API development tools`

مقدارهای `api_id` و `api_hash` را بگیر.

## 3) گرفتن Telegram SESSION_STRING

در کامپیوتر یک پوشه بساز و این پروژه را داخلش قرار بده.

در CMD همان پوشه:

```cmd
py -m pip install -r requirements.txt
py make_session.py
```

شماره، کد تلگرام و اگر 2-Step Verification داری، رمز آن را وارد کن.

در پایان یک خط طولانی به نام `SESSION_STRING` می‌دهد.

این مقدار فوق‌العاده محرمانه است. آن را داخل چت برای کسی نفرست.

## 4) پیدا کردن ADMIN_ID

برای سادگی از `@userinfobot` عدد User ID خودت را بگیر.

مثلاً:

```text
123456789
```

این همان `ADMIN_ID` است.

## 5) ساخت repository در GitHub

یک repository **Public** بساز، مثلاً:

`telegram-profile-rotator`

Public بودن repo فقط برای رایگان بودن runner است؛ **هیچ Secret یا SESSION_STRING را داخل فایل‌های repo نگذار.**

کل فایل‌های این پروژه را داخل repo آپلود کن و push کن.

## 6) افزودن Secrets

داخل repository برو:

`Settings → Secrets and variables → Actions → New repository secret`

این ۵ مورد را بساز:

```text
API_ID
API_HASH
SESSION_STRING
BOT_TOKEN
ADMIN_ID
```

مقدار واقعی هرکدام را داخل همان Secret قرار بده.

## 7) فعال کردن Actions

برو به تب:

`Actions`

workflow با نام:

`Telegram Profile Rotator`

باید دیده شود.

برای تست می‌توانی روی:

`Run workflow`

بزنی.

## 8) استفاده از ربات

به ربات مدیریتی خودت برو و:

```text
/start
```

### اضافه کردن پروفایل

اول:

```text
/add Makima_Control_Devil_Queen
```

بعد **عکس Makima** را برای ربات بفرست.

تمام شد.

پروفایل دیگری:

```text
/add Portgas_D_Ace_Fire_Fist
```

بعد عکس Ace را بفرست.

### روش سریع‌تر

می‌توانی عکس را مستقیم با Caption بفرستی:

```text
Makima_Control_Devil_Queen
```

ربات عکس + username را با هم ذخیره می‌کند.

## فرمان‌ها

```text
/add USERNAME
/list
/delete 3
/clear
/pause
/resume
/status
/help
```

## ترتیب چرخش

مثلاً اگر سه پروفایل داشته باشی:

```text
01 Makima + Makima_Control_Devil_Queen
02 Ace + Portgas_D_Ace_Fire_Fist
03 Zoro + Roronoa_Zoro_King_Of_Hell
```

چرخش می‌شود:

```text
01 → 02 → 03 → 01 → ...
```

هر چرخش حدود ۱۰ دقیقه بعد انجام می‌شود.

## اطلاعات عکس کجا ذخیره می‌شود؟

عکس‌ها دوباره روی سرور ذخیره نمی‌شوند. ربات Telegram یک `file_id` برای عکس دارد و پروژه همان شناسه را در state نگه می‌دارد. Telegram مستند کرده که `file_id` برای دانلود یا استفادهٔ مجدد از فایل قابل استفاده است.

وضعیت پروژه به‌صورت یک پیام با marker مخصوص در **Saved Messages خود اکانتت** نگه‌داری می‌شود؛ بنابراین لازم نیست usernames یا عکس‌ها را در GitHub commit کنیم.

## هشدار مهم

تغییر username و عکس به‌صورت خیلی مکرر می‌تواند باعث rate limit / `FloodWait` تلگرام شود. برنامه خطای FloodWait را می‌گیرد و زمان بعدی را عقب می‌اندازد؛ بنابراین «دقیقاً هر ۱۰ دقیقه» تضمین قطعی نیست.

همچنین username باید طبق قواعد فعلی تلگرام معتبر و آزاد باشد: ۵ تا ۳۲ کاراکتر و فقط حروف انگلیسی، عدد و `_`.

## امنیت

- `BOT_TOKEN` را کسی نبیند.
- `API_HASH` را کسی نبیند.
- مخصوصاً `SESSION_STRING` را کسی نبیند؛ این credential به اکانت تلگرام تو دسترسی می‌دهد.
- Secretها را فقط در GitHub Actions Secrets نگه دار.
- فایل `.session` یا خروجی Session را داخل GitHub commit نکن.
