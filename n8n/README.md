# n8n Marketing Agent Pipeline

This folder contains the `marketing_workflow.json` file, which is a structural skeleton for replicating your Python pipeline directly in n8n.

### How to use this:
1. Open your paid n8n dashboard.
2. Create a new workflow.
3. Click **Import from File** (or copy-paste the contents of `marketing_workflow.json` into the editor).
4. The visual nodes will appear showing the exact flow of data from Apps Script -> Scraping -> Groq -> Apps Script.

### Required Configuration in n8n
Because n8n requires specific credentials, you must configure the following manually:

1. **Apps Script URL and Token**: Since n8n Cloud handles credentials differently, the absolute easiest way to connect your Google Sheet is to hardcode the URL. 
   - Double-click the **"Fetch Competitors from Google Sheets"** node. Delete `={{ $env.APPS_SCRIPT_URL }}?action=get_config&token={{ $env.APPS_SCRIPT_TOKEN }}` and paste your actual Apps Script Web App URL, making sure it ends with `?action=get_config&token=YOUR_TOKEN_HERE`.
   - Double-click the **"Publish to Google Docs (Apps Script)"** node. Do the same thing for the URL field, but ensure it ends with `?action=publish_doc&token=YOUR_TOKEN_HERE`.
2. **Groq Authentication**: On the "Analyze with Groq LLM" node, click the "Credential for Header Auth" dropdown and select "Create New Credential". Set the Name to `Authorization` and the Value to `Bearer YOUR_GROQ_API_KEY`.
3. **Markdown Formatting**: In the "Format JSON to Markdown" Code node, you will need to map the JSON fields returned by Groq into the Markdown string template, similar to what `pipeline/publish.py` does in Python.

### Connect Dashboard to n8n Webhook
Once you save the workflow in n8n, click on the **Webhook** node and copy the **Production URL**. 

Then, go to `appscript/Code.js` in your project and update the URL in `apiTriggerJob()`:

```javascript
  // Trigger the n8n Webhook
  try {
    const url = "YOUR_N8N_WEBHOOK_URL_HERE";
    const options = {
      method: "post",
      muteHttpExceptions: true
    };
    UrlFetchApp.fetch(url, options);
  } catch(e) {
    Logger.log("Failed to ping Webhook: " + e.toString());
  }
```
Run `clasp push` and `clasp deploy` and your dashboard button will trigger your new n8n pipeline!
