import { exec, execSync } from "child_process";
import TelegramBot from "node-telegram-bot-api";
import fs from "fs";
import "dotenv/config";

const token = process.env.TELEGRAM_BOT_TOKEN;
const host = process.env.BROKER_HOST;
const port = process.env.BROKER_PORT;
const username = process.env.BROKER_USERNAME;
const password = process.env.BROKER_PASSWORD;

const bot = new TelegramBot(token, { polling: true });

const commlibCliBaseCmd = `commlib-cli --host ${host} --port ${port} --username ${username} --password ${password} --btype mqtt`;

const BOTS_INFO_MAP = new Map();

bot.on("polling_error", console.log);

// Check if commlib-cli is installed
try {
  execSync("commlib-cli --help", { stdio: "ignore" });
} catch (error) {
  console.error(
    `commlib-cli is not installed. Exiting process. Error: ${error}`
  );
  process.exit(1);
}

// Read and parse bots-info.json file and populate the BOTS_INFO_MAP
try {
  const botsInfo = JSON.parse(
    fs.readFileSync(process.env.BOTS_INFO_FILE, "utf8")
  );
  botsInfo.forEach((bot) => {
    BOTS_INFO_MAP.set(bot.id, bot);
  });
} catch (error) {
  console.error("Error reading or parsing bots-info.json:", error);
}

// Matches "/balance <bot-ID>"
bot.onText(/\/balance (\w+)/, (msg, match) => {
  const chatId = msg.chat.id;
  const botId = match[1];
  const data = getFormattedBalance(botId);
  bot.sendMessage(chatId, data, { parse_mode: "Markdown" });
});

// Matches "/status <bot-ID>"
bot.onText(/\/status (\w+)?/, async (msg, match) => {
  const chatId = msg.chat.id;
  const botId = match[1];
  const statuses = await getStatuses([botId]);
  const message = formatStatuses(statuses);
  bot.sendMessage(chatId, message, { parse_mode: "Markdown" });
});

// Matches "/status_all"
bot.onText(/\/status_all/, async (msg) => {
  const chatId = msg.chat.id;
  const botIds = Array.from(BOTS_INFO_MAP.keys());
  const statuses = await getStatuses(botIds);
  const message = formatStatuses(statuses);
  bot.sendMessage(chatId, message || "Error!", { parse_mode: "Markdown" });
});

// Matches "/list"
bot.onText(/\/list/, (msg) => {
  const chatId = msg.chat.id;
  const message = formatBotList();
  bot.sendMessage(chatId, message || "Error!", { parse_mode: "Markdown" });
});

// Function to execute the command and get the balance
function getBalance(botId) {
  const stdout = execSync(
    `${commlibCliBaseCmd} rpcc 'hbot/${botId}/balance' {}`,
    { encoding: "utf8" }
  );
  const jsonString = stdout.replace(/'/g, '"');
  const data = JSON.parse(jsonString);
  return data;
}

function getFormattedBalance(botId) {
  try {
    const data = getBalance(botId);
    return formatBalance(data);
  } catch (error) {
    console.log("error:", error);
    return "Error!";
  }
}

// Function to execute the command and get the status asynchronously
async function getStatus(botId) {
  return new Promise((resolve) => {
    exec(
      `${commlibCliBaseCmd} rpcc 'hbot/${botId}/status' {}`,
      { encoding: "utf8" },
      (error, stdout) => {
        if (error) {
          console.error("Error:", error);
          resolve("Error!");
        } else {
          try {
            const jsonString = stdout.replace(/'/g, '"');
            const data = JSON.parse(jsonString);
            resolve(data.msg || "OK!");
          } catch (parseError) {
            console.error("Parse Error:", parseError);
            resolve("Error!");
          }
        }
      }
    );
  });
}

// Function to format balance data into a message
function formatBalance(data) {
  // Remove the exchanges_total key
  delete data.data.exchanges_total;

  const exchanges = Object.keys(data.data);
  let message = "";

  exchanges.forEach((exchange) => {
    message += `Exchange: *${exchange}*\n`;
    data.data[exchange].balances.forEach((balance) => {
      message += `  *${balance.Asset}*: _${balance.Total} (${balance["Total ($)"]}$)_\n`;
    });
    message += `Total: *${data.data[exchange].total}*$\nAllocated: *${data.data[exchange].allocated_percentage}*\n\n`;
  });

  return message;
}

// Function to get statuses of specified bots from BOTS_INFO_MAP asynchronously
async function getStatuses(botIds) {
  const statuses = await Promise.all(
    botIds.map(async (botId) => {
      const botInfo = BOTS_INFO_MAP.get(botId);
      const status = await getStatus(botId);
      return { name: botInfo?.name, status: status };
    })
  );
  return statuses;
}

// Function to format all bot statuses into a message
function formatStatuses(data) {
  let message = "";
  data.forEach((bot) => {
    message += `Bot Name: *${bot.name}*\nStatus: *${bot.status}*\n\n`;
  });
  return message;
}

// Function to format the bot list into a message
function formatBotList() {
  let message = "";
  BOTS_INFO_MAP.forEach((botInfo, botId) => {
    message += `Bot ID: *${botId}*\nBot Name: *${
      botInfo.name
    }*\nAccounts: *${botInfo.accounts.join(", ")}*\n\n`;
  });
  return message;
}
