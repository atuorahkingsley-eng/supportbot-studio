---
title: Widget Installation Guide
version: 1.0
owner: Kay — SupportBot Studio
last_updated: 2026-05-15
audience: Clients and internal reference
---

# Installing Your SupportBot Widget

The widget script is a single line of code you paste into your website. It loads the chat bubble in the bottom-right corner of every page automatically — no per-page setup. It goes just before the closing `</body>` tag because that's the last thing the browser reads, so the chat appears only after your page content has loaded and never blocks anything else.

Once the script is live, the widget shows up on every page of your site without further action.

**Generic script template — use this everywhere:**

```html
<script
  src="https://supportbot-studio.onrender.com/widget.js"
  data-bot-id="YOUR_BOT_ID">
</script>
```

> Replace `YOUR_BOT_ID` with the bot ID provided in your welcome email. Your bot ID looks like: `bot_abc123xyz`.

---

## 🛍️ Shopify

**Difficulty:** Easy
**Time to install:** 3 minutes
**Prerequisites:** Shopify admin access, theme editor access

### Steps

1. Log into your Shopify admin (`yourstorename.myshopify.com/admin`).
2. Click **Online Store** in the left sidebar.
3. Click **Themes**.
4. Find your current active theme (marked with a green **Active** badge).
5. Click the three dots (`...`) next to it.
6. Click **Edit code**.
7. In the left file panel under **Layout**, click `theme.liquid`.
8. Press `Ctrl+F` (or `Cmd+F` on Mac) to open search.
9. Type: `</body>`
10. Click just before `</body>` to place your cursor there.
11. Paste your widget script:

    ```html
    <script
      src="https://supportbot-studio.onrender.com/widget.js"
      data-bot-id="YOUR_BOT_ID">
    </script>
    ```

12. Click **Save** (top right).
13. Visit your store in a new tab.

✅ **You'll know it worked when:** the chat bubble appears (in your brand color) in the bottom-right corner of your store.

⚠️ **Watch out:** Do not paste the script inside the `<head>` section — it must go just before `</body>` at the very end of the file.

---

## 🌐 WordPress

Two methods — use **Method A** if possible.

### Method A: Plugin (Recommended)

**Difficulty:** Easy
**Time to install:** 5 minutes
**Prerequisites:** WordPress admin access, ability to install plugins

#### Steps

1. Log into WordPress admin (`yoursite.com/wp-admin`).
2. Go to **Plugins → Add New**.
3. Search for: `Insert Headers and Footers`.
4. Install and **Activate** the plugin by WPBeginner.
5. Go to **Settings → Insert Headers and Footers**.
6. Find the **Scripts in Footer** section.
7. Paste your widget script there:

    ```html
    <script
      src="https://supportbot-studio.onrender.com/widget.js"
      data-bot-id="YOUR_BOT_ID">
    </script>
    ```

8. Click **Save**.

✅ **You'll know it worked when:** the chat bubble appears (in your brand color) on every page of your WordPress site.

⚠️ **Watch out:** If your hosting provider runs caching (e.g. WP Rocket, LiteSpeed Cache), purge the cache after saving — otherwise the script won't show up for a few minutes.

### Method B: Theme Editor (Advanced)

**Difficulty:** Medium
**Time to install:** 5 minutes
**Prerequisites:** WordPress admin, theme editor access

#### Steps

1. Go to **Appearance → Theme File Editor**.
2. In the right panel under **Theme Files**, find and click `footer.php`.
3. Find the line that says `</body>`.
4. Paste your script just before it:

    ```html
    <script
      src="https://supportbot-studio.onrender.com/widget.js"
      data-bot-id="YOUR_BOT_ID">
    </script>
    ```

5. Click **Update File**.

✅ **You'll know it worked when:** the chat bubble appears on every page of your site.

⚠️ **Watch out:** If your theme updates, this change may be overwritten. Use **Method A** (plugin) to avoid this — or use a child theme.

---

## 🎨 Webflow

**Difficulty:** Easy
**Time to install:** 3 minutes
**Prerequisites:** Webflow project editor access

### Steps

1. Open your Webflow project.
2. Click the gear icon (⚙️) for **Project Settings**.
3. Click the **Custom Code** tab.
4. Scroll to the **Footer Code** section.
5. Paste your widget script:

    ```html
    <script
      src="https://supportbot-studio.onrender.com/widget.js"
      data-bot-id="YOUR_BOT_ID">
    </script>
    ```

6. Click **Save Changes**.
7. Click **Publish → Publish to your domain**.

✅ **You'll know it worked when:** after publishing, you visit your live site and see the chat bubble (in your brand color) in the bottom-right corner.

⚠️ **Watch out:** Changes in Webflow only go live after you publish. If the bubble doesn't appear, check that you clicked **Publish** after saving — the Webflow designer preview doesn't run custom code.

---

## 🌟 Wix

**Difficulty:** Easy
**Time to install:** 5 minutes
**Prerequisites:** Wix account **owner** access (Editor access alone is not enough — must be the account owner)

### Steps

1. Log into your Wix account.
2. Go to your site dashboard.
3. Click **Settings** in the left menu.
4. Click **Custom Code**.
5. Click **+ Add Custom Code** (top right).
6. Paste your widget script:

    ```html
    <script
      src="https://supportbot-studio.onrender.com/widget.js"
      data-bot-id="YOUR_BOT_ID">
    </script>
    ```

7. In the **Add Code to Pages** section, select **All Pages**.
8. In **Place Code in**, select **Body - end**.
9. Give it a name: `SupportBot Widget`.
10. Click **Apply**.

✅ **You'll know it worked when:** the chat bubble appears (in your brand color) on all pages of your Wix site within 1–2 minutes.

⚠️ **Watch out:** Wix requires account-owner permissions for Custom Code. If you don't see the **Custom Code** option, you're probably logged in as a collaborator rather than the owner.

---

## 🔲 Squarespace

**Difficulty:** Easy
**Time to install:** 3 minutes
**Prerequisites:** Squarespace admin access on a **Business** plan or higher (Personal plan does not support custom code)

### Steps

1. Log into your Squarespace account.
2. Go to your site editor.
3. Click **Settings** (gear icon).
4. Click **Advanced**.
5. Click **Code Injection**.
6. Find the **Footer** section.
7. Paste your widget script:

    ```html
    <script
      src="https://supportbot-studio.onrender.com/widget.js"
      data-bot-id="YOUR_BOT_ID">
    </script>
    ```

8. Click **Save**.

✅ **You'll know it worked when:** the chat bubble appears (in your brand color) on every page of your Squarespace site.

⚠️ **Watch out:** Code Injection is only available on **Business plan and above**. If you don't see the option, upgrade your Squarespace plan first.

---

## 🌐 GoDaddy Website Builder

**Difficulty:** Medium
**Time to install:** 5 minutes
**Prerequisites:** GoDaddy account access

### Steps

1. Log into your GoDaddy account.
2. Go to **My Products → Website Builder**.
3. Click **Edit Website**.
4. Click **Settings** (gear icon).
5. Click **SEO** (this is where GoDaddy puts custom code).
6. Scroll to **Footer Scripts**.
7. Paste your widget script:

    ```html
    <script
      src="https://supportbot-studio.onrender.com/widget.js"
      data-bot-id="YOUR_BOT_ID">
    </script>
    ```

8. Click **Save → Publish**.

✅ **You'll know it worked when:** the chat bubble appears (in your brand color) after publishing.

⚠️ **Watch out:** GoDaddy's custom-code location moves between versions. If you don't see **Footer Scripts** under SEO, check under **Advanced Settings** or **Website Settings**. If it's nowhere, you may be on a plan tier that doesn't include custom code — contact GoDaddy support to confirm.

---

## 🛒 BigCommerce

**Difficulty:** Medium
**Time to install:** 5 minutes
**Prerequisites:** BigCommerce store admin access

### Steps

1. Log into BigCommerce admin.
2. Go to **Storefront → Script Manager**.
3. Click **Create a Script**.
4. Fill in:
   - **Name:** `SupportBot Widget`
   - **Description:** `AI customer support widget`
   - **Location on page:** `Footer`
   - **Select pages where script will be added:** `All pages`
   - **Script type:** `Script`
5. Paste your widget script in the **Script contents** box:

    ```html
    <script
      src="https://supportbot-studio.onrender.com/widget.js"
      data-bot-id="YOUR_BOT_ID">
    </script>
    ```

6. Click **Save**.

✅ **You'll know it worked when:** the chat bubble appears (in your brand color) on all store pages.

⚠️ **Watch out:** Script Manager requires you to choose a location explicitly — make sure it's **Footer**, not **Header**. Scripts in the header can slow your store's first paint.

---

## 💻 Custom / Plain HTML Website

**Difficulty:** Easy
**Time to install:** 2 minutes
**Prerequisites:** Access to your HTML files or hosting file manager

### Steps

1. Open your main HTML file (usually `index.html` or `default.html`) — or your shared template / layout file if you use one.
2. Find the closing `</body>` tag (near the bottom of the file).
3. Paste your script just before it:

    ```html
    <!DOCTYPE html>
    <html>
    <head>
      <!-- your existing head content -->
    </head>
    <body>

      <!-- all your page content -->

      <!-- SupportBot Widget — paste here -->
      <script
        src="https://supportbot-studio.onrender.com/widget.js"
        data-bot-id="YOUR_BOT_ID">
      </script>
    </body>
    </html>
    ```

4. Save the file.
5. Upload to your hosting if editing locally.

✅ **You'll know it worked when:** the chat bubble appears (in your brand color) when you open the page in a browser.

⚠️ **Watch out:** If your site has multiple HTML files, paste the script in each one — or better, create a shared include / template file that all pages use, so future updates only need to happen once.

---

## 🖼️ Framer

**Difficulty:** Easy
**Time to install:** 3 minutes
**Prerequisites:** Framer project access

### Steps

1. Open your Framer project.
2. Click the gear icon for **Site Settings**.
3. Click **General**.
4. Scroll to **Custom Code**.
5. Find the **End of `<body>` tag** section.
6. Paste your widget script:

    ```html
    <script
      src="https://supportbot-studio.onrender.com/widget.js"
      data-bot-id="YOUR_BOT_ID">
    </script>
    ```

7. Click **Save**.
8. **Publish** your site.

✅ **You'll know it worked when:** the chat bubble appears (in your brand color) on your live Framer site after publishing.

⚠️ **Watch out:** Framer's preview mode doesn't run custom code — you must publish to test. If you don't have a custom domain attached, Framer publishes to a `*.framer.app` URL where the widget will also work.

---

## 👻 Ghost

**Difficulty:** Medium
**Time to install:** 5 minutes
**Prerequisites:** Ghost admin access

### Steps

1. Log into Ghost admin (`yoursite.com/ghost`).
2. Go to **Settings** (gear icon).
3. Click **Code injection**.
4. Find the **Site Footer** section.
5. Paste your widget script:

    ```html
    <script
      src="https://supportbot-studio.onrender.com/widget.js"
      data-bot-id="YOUR_BOT_ID">
    </script>
    ```

6. Click **Save**.

✅ **You'll know it worked when:** the chat bubble appears (in your brand color) on all your Ghost pages and posts.

⚠️ **Watch out:** Code Injection is a Ghost Pro / self-hosted feature. If you're on the free Ghost Starter plan, the option won't be visible — you'll need to upgrade or self-host.

---

## Testing Your Widget

Run through these steps right after pasting the script, on any platform:

1. Open your website in a **private / incognito** browser window (this avoids cached versions).
2. Look for the chat bubble in the bottom-right corner.
3. Click it — the chat window should open.
4. Type: `Hello`.
5. Wait for a response from the bot.
6. If the bot responds — installation is complete.

### If the bubble doesn't appear

| Check | How |
|---|---|
| Script pasted correctly | Re-check the code — no extra characters, no missing `<script>` / `</script>` tags |
| Bot ID is correct | Check your welcome email for the exact ID |
| Changes published | Some platforms (Webflow, Wix, Framer) need an explicit publish step after saving |
| Browser cache | Try an incognito window or hard-refresh (`Ctrl+Shift+R` / `Cmd+Shift+R`) |
| Plan active | Log into your SupportBot dashboard and confirm your plan is active |

If you've worked through the checklist and the bubble still isn't there, open your browser's developer console (`F12` → **Console** tab) and look for any red error mentioning `supportbot` or `widget.js` — that message tells us exactly what's wrong. Forward the screenshot and we'll fix it.

---

## Need Help Installing?

Installation taking longer than expected? Reply to your welcome email or book a 15-minute installation call:

**[Book a 15-minute installation call](https://calendly.com/atuorahkingsley/supportbot-studio-demo)**

We can install the widget for you remotely on any platform — included in your onboarding fee.

---

*Last updated: 2026-05-15*
*SupportBot Studio — [supportbot-studio.onrender.com](https://supportbot-studio.onrender.com)*
*Questions? Reply to your welcome email.*
