require('dotenv').config();
const axios = require('axios');
const FormData = require('form-data');
const { v4: uuidv4 } = require('uuid');
const dns = require('dns').promises;
const fs = require('fs');
const path = require('path');
const { parse } = require('csv-parse');
const pLimit = require('p-limit');

// --- IMPORT YOUR NEW MODULES ---
// Note the paths: '../' goes up to the root, './' stays in the current folder.
const { logDebug, logFilePath } = require('../logger');
const { parseAndSaveSimpleResults } = require('./realtime_parse');

// Define paths relative to the project structure
const INPUT_OUTPUT_DIR = path.join(__dirname, '..', 'x12_input_and_results');

// Function to attempt DNS resolution with multiple DNS servers
async function checkDNS(domain) {
    const dnsServers = [
        { server: '8.8.8.8', name: 'Google DNS' },
        { server: '1.1.1.1', name: 'Cloudflare DNS' },
        { server: '208.67.222.222', name: 'OpenDNS' }
    ];
    for (const { server, name } of dnsServers) {
        logDebug('info', `Attempting DNS resolution for ${domain} using ${name} (${server})`);
        try {
            dns.setServers([server]);
            const addresses = await dns.resolve4(domain);
            logDebug('info', `DNS resolved for ${domain} using ${name}`, { addresses });
            return true;
        } catch (error) {
            logDebug('error', `DNS resolution failed with ${name} (${server})`, { error: error.message });
        }
    }
    logDebug('error', `All DNS resolution attempts failed for ${domain}`);
    return false;
}

// Function to generate a random N-digit number
function generateRandomNumber(digits) {
    const min = Math.pow(10, digits - 1);
    const max = Math.pow(10, digits) - 1;
    return Math.floor(min + Math.random() * (max - min + 1));
}

// Function to read member IDs from CSV
async function readMemberIds(csvFilePath) {
    return new Promise((resolve, reject) => {
        const memberIds = [];
        logDebug('info', `Reading member IDs from ${csvFilePath}`);
        fs.createReadStream(csvFilePath)
            .pipe(parse({ columns: false, trim: true }))
            .on('data', (row) => {
                const memberId = row[0];
                if (memberId && /^\d{12}$/.test(memberId)) {
                    memberIds.push(memberId);
                } else {
                    logDebug('warn', `Invalid member ID skipped (must be 12 digits)`, { memberId });
                }
            })
            .on('end', () => {
                logDebug('info', `Completed reading CSV. Found ${memberIds.length} valid member IDs.`);
                resolve(memberIds);
            })
            .on('error', (error) => {
                logDebug('error', `Failed to read CSV file`, { error: error.message });
                reject(new Error(`Failed to read CSV file: ${error.message}`));
            });
    });
}

// Function to generate X12 270 payload for a single member ID
async function generateX12Payload(memberId) {
    // This function remains unchanged
    const now = new Date();
    const date = now.toISOString().slice(0, 10).replace(/-/g, '');
    const time = now.toISOString().slice(11, 16).replace(':', '');
    const controlNumber = `1000${generateRandomNumber(5)}`;
    const groupControlNumber = generateRandomNumber(5);
    const transactionId = `1000${generateRandomNumber(4)}`;
    const eligibilityDate = date;
    const isaDate = date.slice(2);
    const transactionSegments = [
        `ST*270*1240*005010X279A1~`, `BHT*0022*13*${transactionId}*${date}*${time}~`, `HL*1**20*1~`,
        `NM1*PR*2*INDIANA HEALTH COVERAGE PROGRAM*****PI*IHCP~`, `HL*2*1*21*1~`,
        `NM1*1P*2*ABSOLUTE CAREGIVERS LLC*****SV*300024773 ~`, `HL*3*2*22*0~`, `TRN*1*93175-012552-3*9877281234~`,
        `NM1*IL*1******MI*${memberId}~`, `DTP*291*D8*${eligibilityDate}~`, `EQ*30~`
    ];
    const seSegment = `SE*${transactionSegments.length + 1}*1240~`;
    const payloadSegments = [
        `ISA*00*          *00*          *ZZ*A367           *ZZ*IHCP           *${isaDate}*${time}*^*00501*${controlNumber}*0*P*:~`,
        `GS*HS*A367*IHCP*${date}*${time}*${groupControlNumber}*X*005010X279A1~`, ...transactionSegments, seSegment,
        `GE*1*${groupControlNumber}~`, `IEA*1*${controlNumber}~`
    ];
    fs.writeFileSync('payload.x12', payloadSegments.join('\r\n'));
    return Buffer.from(payloadSegments.join('\r\n'), 'utf8');
}

// Function to send a single 270 request for one member ID
async function send270Request(memberId, domain, retryCount = 3) {
    // The loop now handles generating a fresh request for each attempt.
    for (let attempt = 1; attempt <= retryCount; attempt++) {
        logDebug('info', `Preparing request (Attempt ${attempt}) for member`, { memberId });

        // --- ALL REQUEST GENERATION MOVED INSIDE THE LOOP ---
        const payload = await generateX12Payload(memberId);
        const form = new FormData();
        form.append('PayloadType', 'X12_270_Request_005010X279A1');
        form.append('ProcessingMode', 'RealTime');
        form.append('PayloadID', uuidv4()); // A NEW UUID IS GENERATED FOR EACH ATTEMPT
        form.append('TimeStamp', new Date().toISOString());
        form.append('UserName', 'asll4982');
        form.append('Password', process.env.HCP_PASSWORD); // Make sure this is now correct in .env!
        form.append('SenderID', 'A367');
        form.append('ReceiverID', 'IHCP');
        form.append('CORERuleVersion', '2.2.0');
        form.append('Payload', payload, { contentType: 'text/plain; charset=utf-8' });

        const requestBody = form.getBuffer();
        const requestHeaders = {
            ...form.getHeaders(),
            'Content-Length': requestBody.length,
        };

        const axiosConfig = {
            headers: requestHeaders,
            timeout: 10000,
        };
        // --- END OF MOVED LOGIC ---

        logDebug('info', `Sending request (Attempt ${attempt})`, { memberId });
        try {
            const response = await axios.post(`https://${domain}/HP.Core.mime/CoreTransactions.aspx`, requestBody, axiosConfig);

            logDebug('info', `Request successful`, { memberId, status: response.status });
            logDebug('info', 'Raw response data', { memberId, data: response.data });

            // If we get a successful response, we break the loop and return the result.
            return { memberId, status: response.status, data: response.data };

        } catch (error) {
            const errorDetails = { memberId, attempt, errorCode: error.code, errorMessage: error.message, status: error.response?.status };
            if (error.response) {
                errorDetails.responseData = error.response.data;
            }
            logDebug('error', `Request failed on attempt ${attempt}`, errorDetails);

            // If this was the last attempt, return the error
            if (attempt === retryCount) {
                return { memberId, status: 'error', error: error.message, details: errorDetails };
            }

            // Wait before the next attempt
            await new Promise(resolve => setTimeout(resolve, 1000 * attempt));
        }
    }
}

// Main function to process all patients
async function processAllPatients(csvFileName, concurrencyLimit = 10) {
    const csvFilePath = path.join(INPUT_OUTPUT_DIR, csvFileName);
    logDebug('info', 'Starting patient processing', { csvFilePath, concurrencyLimit });
    const domain = 'coresvc.indianamedicaid.com';

    try {
        // Use the imported logFilePath to clear the log
        if (fs.existsSync(logFilePath)) {
            fs.writeFileSync(logFilePath, '');
        }
        logDebug('info', 'Cleared debug log file');
    } catch (error) {
        logDebug('error', 'Failed to clear debug log file', { error: error.message });
    }

    if (!await checkDNS(domain)) {
        logDebug('error', 'Aborting due to DNS resolution failure.');
        return; // Use return instead of process.exit for better integration
    }

    const memberIds = await readMemberIds(csvFilePath).catch(err => {
        logDebug('error', 'Failed to read member IDs, aborting.', { error: err.message });
    });
    if (!memberIds || memberIds.length === 0) {
        logDebug('error', 'No valid member IDs found in CSV file, aborting.');
        return;
    }

    logDebug('info', `Processing ${memberIds.length} member IDs with concurrency of ${concurrencyLimit}.`);
    const limit = pLimit(concurrencyLimit);
    const results = await Promise.all(memberIds.map(id => limit(() => send270Request(id, domain))));

    try {
        const rawResultsPath = path.join(INPUT_OUTPUT_DIR, 'results.json');
        fs.writeFileSync(rawResultsPath, JSON.stringify(results, null, 2));
        logDebug('info', `Raw results saved to ${rawResultsPath}`);
    } catch (error) {
        logDebug('error', 'Error saving raw results', { error: error.message });
    }

    // *** CALL THE IMPORTED PARSING FUNCTION HERE ***
    parseAndSaveSimpleResults(results);

    logDebug('info', 'All patients processed.');
    return results;
}

// Run the process with the correct CSV file name from your input directory
processAllPatients('realtime.csv', 1)
    .catch(err => {
        logDebug('error', 'Fatal error during processing', { error: err.message, stack: err.stack });
    });