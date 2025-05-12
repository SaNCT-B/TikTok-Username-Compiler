const express = require('express');
const bodyParser = require('body-parser');
const WebSocket = require('ws');
const { WebcastPushConnection } = require('tiktok-live-connector');


const app = express();
const port = process.argv[2] || 8080; // Change default port to 8080

let currentKeyword = '';
let viewersSet = new Set();
let wsClient = null;

app.use(bodyParser.json());

const server = app.listen(port, () => {
    console.log(`🚀 Server is running on http://localhost:${port}`);
});

const shutdown = () => {
    console.log('🛑 Shutting down server...');
    if (tiktokConnection) {
        tiktokConnection.disconnect();
        console.log('🔌 TikTok connection closed');
    }
    if (wsClient) {
        wsClient.close();
        console.log('❌ WebSocket client closed');
    }
    server.close(() => {
        console.log('✅ HTTP server closed');
        process.exit(0);
    });
};

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

// WebSocket setup
const wss = new WebSocket.Server({ server });

// Heartbeat function to keep WebSocket alive
function heartbeat() {
    this.isAlive = true;
}

wss.on('connection', ws => {
    console.log('🔌 GUI connected via WebSocket');
    ws.isAlive = true;

    // Listen for pong messages to confirm the client is alive
    ws.on('pong', heartbeat);

    wsClient = ws;

    ws.on('close', () => {
        console.log('❌ GUI WebSocket disconnected');
        wsClient = null;
    });

    ws.on('error', error => {
        console.log(`❌ WebSocket error: ${error}`);
    });
});

// Periodically check if WebSocket clients are alive
const interval = setInterval(() => {
    wss.clients.forEach(ws => {
        if (!ws.isAlive) {
            console.log('❌ Terminating unresponsive WebSocket client');
            return ws.terminate();
        }

        ws.isAlive = false;
        ws.ping(); // Send a ping to the client
    });
}, 30000); // Check every 30 seconds

// Cleanup interval on server shutdown
server.on('close', () => {
    clearInterval(interval);
});

function createKeywordMatcher(keyword) {
    const normalizeText = (text) => {
        return text.toLowerCase()
            .replace(/['']/g, "'")    // normalize apostrophes to single type
            .replace(/\s+/g, ' ')     // normalize spaces
            .trim();
    };

    // Normalize input keyword
    const normalizedKeyword = normalizeText(keyword);
    const words = normalizedKeyword.split(/\s+/);
    
    if (words.length > 1) {
        // Multi-word phrases (must be the entire message, ignoring punctuation between words)
        const phrasePattern = words
            .map(word => {
                const baseWord = word.replace(/'/g, ""); // Remove apostrophes
                const escaped = baseWord.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); // Escape special characters
                return `${escaped}(?:'s|s)?`; // Allow optional 's or s suffix
            })
            .join("[\\s]*"); // Allow spaces between words

        return new RegExp(
            `^${phrasePattern}[!.?]*[\\u{1F300}-\\u{1F9FF}]*$`, // Must match the entire message
            'iu'
        );
    } else {
        // Single-word keywords (must be the entire message)
        const baseWord = words[0].replace(/'/g, ""); // Remove apostrophes
        const escaped = baseWord.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); // Escape special characters

        // Allow repeated characters (e.g., happyyyy but not happiness)
        const repeated = escaped.replace(/(.)\1+/g, '$1{2,}');

        return new RegExp(
            `^(${escaped}(?:'s|s)?|${repeated})[!.?]*[\\u{1F300}-\\u{1F9FF}]*$`, // Must match the entire message
            'iu'
        );
    }
}

// Start TikTok connection
let tiktokConnection = null;

app.post('/start', async (req, res) => {
    const username = req.body.username;
    if (!username) {
        return res.status(400).json({ success: false, error: "Missing username" });
    }

    // Clean up any previous connection
    if (tiktokConnection) {
        try {
            await tiktokConnection.disconnect();
            console.log("🔌 Previous TikTok connection closed");
        } catch (err) {
            console.log("⚠️ Error during disconnect:", err.message);
        }
        tiktokConnection = null;
    }

    const connection = new WebcastPushConnection(username);
    let receivedChat = false;

    // Chat handler
    connection.on('chat', data => {
        receivedChat = true;
        const viewerName = data.nickname || data.uniqueId;
        const messageText = data.comment || '';
        console.log(`${viewerName}: ${messageText}`);

        if (!currentKeyword) return;

        const regex = createKeywordMatcher(currentKeyword);
        if (regex.test(messageText)) {
            if (!viewersSet.has(viewerName)) {
                viewersSet.add(viewerName);
                if (wsClient && wsClient.readyState === WebSocket.OPEN) {
                    wsClient.send(viewerName);
                }
            }
        }
    });

    try {
        const connectResult = await connection.connect();
        console.log("🧪 connect() result:", connectResult);

        // Wait up to 2.5 seconds to see if chat arrives
        await new Promise(resolve => setTimeout(resolve, 2000));

        if (!receivedChat) {
            console.log(`❌ @${username} is not live (no chat received)`);
            await connection.disconnect();
            return res.status(400).json({ success: false, error: "User is not live" });
        }

        console.log(`✅ Connected to @${username}`);
        tiktokConnection = connection;
        return res.json({ success: true });

    } catch (err) {
        console.log(`❌ Error connecting to @${username}:`, err.message);
        return res.status(400).json({ success: false, error: err.message });
    }
});


// Set keyword
app.post('/keyword', (req, res) => {
    const { keyword } = req.body;
    if (!keyword) return res.status(400).send('Keyword required.');
    currentKeyword = keyword.trim();
    viewersSet.clear();
    console.log(`🔑 Keyword set: ${currentKeyword}`);
    res.send('Keyword set');
});

// Reset keyword endpoint
app.post('/clearKeyword', (req, res) => {
    currentKeyword = '';
    viewersSet.clear();
    console.log('🔑 Keyword cleared');
    
    // Send reset message to GUI
    if (wsClient && wsClient.readyState === WebSocket.OPEN) {
        wsClient.send('clearViewers');
    }

    res.send('Keyword cleared');
});

// Add these endpoints
app.post('/disconnect', async (req, res) => {
    if (tiktokConnection) {
        await tiktokConnection.disconnect();
        tiktokConnection = null;
    }
    res.send('Disconnected from TikTok stream');
});

// Shutdown endpoint
app.post('/shutdown', (req, res) => {
    res.send('Shutting down...');
    shutdown();
});
