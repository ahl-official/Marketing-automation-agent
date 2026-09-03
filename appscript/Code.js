const SPREADSHEET_ID = "14Cm7he6avUB5pgOoIwKniYGPTEclTrQCFwNHCv7ZXm4";
const CONFIG_SHEET = 'Config';
const ARCHIVE_SHEET = 'Archive';
const SETTINGS_SHEET = 'Settings';
const DASHBOARD_DATA_SHEET = 'DashboardData';

function getSpreadsheet() {
  return SpreadsheetApp.openById(SPREADSHEET_ID);
}

function verifyToken(e) {
  const providedToken = e.parameter.token;
  const expectedToken = PropertiesService.getScriptProperties().getProperty('API_SECRET');
  if (!expectedToken) {
    throw new Error('API_SECRET script property is not set.');
  }
  if (!providedToken || providedToken !== expectedToken) {
    throw new Error('Unauthorized. Missing or incorrect token parameter.');
  }
}

function jsonResponse(obj, statusCode) {
  obj.status = statusCode;
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function initSettings() {
  const ss = getSpreadsheet();
  let sheet = ss.getSheetByName(SETTINGS_SHEET);
  if (!sheet) {
    sheet = ss.insertSheet(SETTINGS_SHEET);
    sheet.appendRow(['Key', 'Value']);
    sheet.appendRow(['job_status', 'IDLE']);
  }
}

function getSettings() {
  initSettings();
  const ss = getSpreadsheet();
  const sheet = ss.getSheetByName(SETTINGS_SHEET);
  const data = sheet.getDataRange().getValues();
  const settings = {};
  for (let i = 1; i < data.length; i++) {
    settings[data[i][0]] = String(data[i][1]).toLowerCase() === 'true' || data[i][1] === true ? true : (String(data[i][1]).toLowerCase() === 'false' || data[i][1] === false ? false : data[i][1]);
  }
  return settings;
}

function updateSettings(newSettings) {
  initSettings();
  const ss = getSpreadsheet();
  const sheet = ss.getSheetByName(SETTINGS_SHEET);
  const data = sheet.getDataRange().getValues();
  
  for (let i = 1; i < data.length; i++) {
    const key = data[i][0];
    if (newSettings.hasOwnProperty(key)) {
      sheet.getRange(i + 1, 2).setValue(newSettings[key]);
    }
  }
  
  for (const key in newSettings) {
    let found = false;
    for (let i = 1; i < data.length; i++) {
      if (data[i][0] === key) found = true;
    }
    if (!found) {
      sheet.appendRow([key, newSettings[key]]);
    }
  }
}

function getCompetitors() {
  const ss = getSpreadsheet();
  const sheet = ss.getSheetByName(CONFIG_SHEET);
  if (!sheet) return [];
  
  const data = sheet.getDataRange().getValues();
  if (data.length < 2) return [];
  
  const headers = data[0].map(h => String(h).trim().toLowerCase());
  const nameCol = headers.indexOf('name');
  const urlCol = headers.indexOf('url');
  
  if (nameCol === -1 || urlCol === -1) return [];
  
  const rows = [];
  for (let i = 1; i < data.length; i++) {
    const name = data[i][nameCol];
    const url = data[i][urlCol];
    if (name && url) {
      rows.push({ name: String(name).trim(), url: String(url).trim() });
    }
  }
  return rows;
}

function updateCompetitors(competitors) {
  const ss = getSpreadsheet();
  let sheet = ss.getSheetByName(CONFIG_SHEET);
  if (!sheet) {
    sheet = ss.insertSheet(CONFIG_SHEET);
  }
  sheet.clear();
  sheet.appendRow(['name', 'url']);
  competitors.forEach(c => {
    sheet.appendRow([c.name, c.url]);
  });
}

function getDashboardData() {
  const ss = getSpreadsheet();
  const sheet = ss.getSheetByName(DASHBOARD_DATA_SHEET);
  if (!sheet) return null;
  const val = sheet.getRange("A1").getValue();
  try {
    return JSON.parse(val);
  } catch(e) {
    return null;
  }
}

function updateDashboardData(data) {
  const ss = getSpreadsheet();
  let sheet = ss.getSheetByName(DASHBOARD_DATA_SHEET);
  if (!sheet) {
    sheet = ss.insertSheet(DASHBOARD_DATA_SHEET);
  }
  sheet.getRange("A1").setValue(JSON.stringify(data));
}

function getArchiveData() {
  const ss = getSpreadsheet();
  const sheet = ss.getSheetByName(ARCHIVE_SHEET);
  if (!sheet) return [];
  
  const data = sheet.getDataRange().getValues();
  if (data.length < 2) return [];
  
  const history = [];
  // Start from 1 to skip header row
  for (let i = 1; i < data.length; i++) {
    if (data[i][0]) {
      let docUrl = String(data[i][1] || "");
      let jsonData = String(data[i][2] || "");
      
      // Handle old format where column 2 was a summary string and not a URL
      if (docUrl && !docUrl.startsWith("http")) {
         docUrl = "";
         jsonData = "";
      }
      
      history.push({
        date: String(data[i][0]),
        docUrl: docUrl,
        jsonData: jsonData
      });
    }
  }
  // Reverse to show newest first
  return history.reverse();
}

function doGet(e) {
  if (!e || !e.parameter || !e.parameter.token) {
    return HtmlService.createTemplateFromFile('Index')
      .evaluate()
      .setTitle('Interactive Analytics Dashboard')
      .addMetaTag('viewport', 'width=device-width, initial-scale=1');
  }

  try {
    verifyToken(e);
    const action = e.parameter.action || 'config';
    
    if (action === 'get_settings') {
      return jsonResponse({ settings: getSettings() }, 200);
    }
    else if (action === 'update_settings') {
      try {
        const payload = JSON.parse(e.postData.contents);
        updateSettings(payload.settings || {});
        return jsonResponse({ success: true }, 200);
      } catch (err) {
        return jsonResponse({ error: err.toString() }, 400);
      }
    }
    else if (action === 'config') {
      return jsonResponse({ rows: getCompetitors(), settings: getSettings() }, 200);
    }
  } catch (err) {
    return jsonResponse({ error: err.message }, 500);
  }
}

function doPost(e) {
  try {
    verifyToken(e);
    const action = e.parameter.action;
    
    if (!e.postData || !e.postData.contents) {
       return jsonResponse({ error: 'Missing POST body.' }, 400);
    }
    const body = JSON.parse(e.postData.contents);
    
    if (action === 'publish_doc') {
      const runDate = body.runDate;
      const report = body.report;
      
      // Save full report JSON to DashboardData sheet for the Frontend Analytics UI
      updateDashboardData(report);
      
      // GENERATE GOOGLE DOC
      const doc = DocumentApp.create('Research Digest - ' + runDate);
      const docBody = doc.getBody();
      docBody.insertParagraph(0, 'Research Digest - ' + runDate).setHeading(DocumentApp.ParagraphHeading.HEADING1);
      
      if (body.formatted_md) {
        docBody.appendParagraph(body.formatted_md);
      } else {
        for (const key in report) {
          if (key === 'metrics' || key === 'sources_appendix') continue; 
          docBody.appendParagraph(key.replace(/_/g, ' ').toUpperCase()).setHeading(DocumentApp.ParagraphHeading.HEADING2);
          if (Array.isArray(report[key])) {
            report[key].forEach(function(item) {
               if (typeof item === 'object') {
                 docBody.appendListItem(JSON.stringify(item));
               } else {
                 docBody.appendListItem(item.toString());
               }
            });
          }
        }
      }
      
      if (report.sources_appendix && report.sources_appendix.length > 0) {
          docBody.appendParagraph("SOURCES APPENDIX").setHeading(DocumentApp.ParagraphHeading.HEADING2);
          report.sources_appendix.forEach(url => {
              docBody.appendListItem(url).setLinkUrl(url);
          });
      }
      
      doc.saveAndClose();
      
      const file = DriveApp.getFileById(doc.getId());
      file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
      
      // Move to a specific folder
      const folderName = "Marketing Research Reports";
      const folders = DriveApp.getFoldersByName(folderName);
      let targetFolder;
      if (folders.hasNext()) {
        targetFolder = folders.next();
      } else {
        targetFolder = DriveApp.createFolder(folderName);
      }
      file.moveTo(targetFolder);
      
      updateSettings({ job_status: 'COMPLETE', last_doc_url: doc.getUrl(), last_run_timestamp: new Date().getTime().toString() });
      
      // NEW ARCHIVE LOGIC: Save the JSON payload so the "Time Machine" history tab can redraw charts
      const ss = getSpreadsheet();
      let archiveSheet = ss.getSheetByName(ARCHIVE_SHEET);
      if (!archiveSheet) {
        archiveSheet = ss.insertSheet(ARCHIVE_SHEET);
        archiveSheet.appendRow(['Date', 'DocURL', 'JSONData']);
      }
      archiveSheet.appendRow([new Date().toLocaleString(), doc.getUrl(), JSON.stringify(report)]);

      return jsonResponse({ docUrl: doc.getUrl() }, 200);
    } 
    else if (action === 'update_status') {
       const newSettings = { job_status: body.status };
       if (body.error) {
           newSettings.last_error = body.error;
       }
       if (body.progress !== undefined) {
           newSettings.job_progress = body.progress;
           newSettings.job_progress_text = body.progress_text;
       }
       updateSettings(newSettings);
       return jsonResponse({ success: true }, 200);
    }
    
    return jsonResponse({ error: 'Unknown action: ' + action }, 400);
    
  } catch (err) {
    return jsonResponse({ error: err.message }, 500);
  }
}

// ----------------------------------------------------
// Functions exposed to Google Apps Script UI (HTML)
// ----------------------------------------------------
function apiGetInitialData() {
  return {
    competitors: getCompetitors(),
    settings: getSettings(),
    dashboardData: getDashboardData(),
    archiveData: getArchiveData() // NEW: Send historical data to frontend
  };
}

function apiGetStatus() {
  return {
    settings: getSettings()
  };
}

function apiUpdateSettings(settingsObj) {
  updateSettings(settingsObj);
  return true;
}

function apiSaveCompetitors(competitors) {
  updateCompetitors(competitors);
  return true;
}

function apiTriggerJob() {
  updateSettings({ job_status: 'PENDING', last_doc_url: '', last_error: '', job_start_timestamp: new Date().getTime().toString(), job_progress: 0, job_progress_text: 'Initializing Agent Workflow...' });
  
  // Trigger the Vercel backend directly so it starts scraping immediately
  try {
    const url = "https://marketing-automation-agent.vercel.app/api/index";
    const options = {
      method: "get",
      muteHttpExceptions: true
    };
    // Fire and forget (Vercel will process it in the background)
    UrlFetchApp.fetch(url, options);
  } catch(e) {
    Logger.log("Failed to ping Vercel: " + e.toString());
  }
  
  return true;
}
