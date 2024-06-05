import { execSync } from "child_process";
import TelegramBot from "node-telegram-bot-api";
import "dotenv/config";

const token = process.env.TELEGRAM_BOT_TOKEN;
const host = process.env.BROKER_HOST;
const port = process.env.BROKER_PORT;
const username = process.env.BROKER_USERNAME;
const password = process.env.BROKER_PASSWORD;

const bot = new TelegramBot(token, { polling: true });

const commlibCliBaseCmd = `commlib-cli --host ${host} --port ${port} --username ${username} --password ${password} --btype mqtt`;

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

// Matches "/balance <bot-ID>"
bot.onText(/\/balance (\w+)/, (msg, match) => {
  const chatId = msg.chat.id;
  const botId = match[1];
  const data = getBalance(botId);
  bot.sendMessage(chatId, data);
});

// Matches "/status <bot-ID>"
bot.onText(/\/status (\w+)/, (msg, match) => {
  const chatId = msg.chat.id;
  const botId = match[1];
  const data = getStatus(botId);
  bot.sendMessage(chatId, data);
});

// Function to execute the command and get the balance
function getBalance(botId) {
  try {
    const stdout = execSync(
      `${commlibCliBaseCmd} rpcc 'hbot/${botId}/balance' {}`,
      { encoding: "utf8" }
    );
    const jsonString = stdout.replace(/'/g, '"');
    const data = JSON.parse(jsonString);
    return formatMessage(data);
  } catch (error) {
    console.log("error:", error);
    return "Error!";
  }
}

// Function to execute the command and get the status
function getStatus(botId) {
  try {
    const stdout = execSync(
      `${commlibCliBaseCmd} rpcc 'hbot/${botId}/status' {}`,
      { encoding: "utf8" }
    );
    const jsonString = stdout.replace(/'/g, '"');
    const data = JSON.parse(jsonString);
    return data.msg || "OK!";
  } catch (error) {
    console.log("error:", error);
    return "Error!";
  }
}

// Function to format balance data into a message
function formatMessage(data) {
  // Remove the exchanges_total key
  delete data.data.exchanges_total;

  const exchanges = Object.keys(data.data);
  let message = "";

  exchanges.forEach((exchange) => {
    message += `Exchange: ${exchange}\n`;
    data.data[exchange].balances.forEach((balance) => {
      message += `  ${balance.Asset}: ${balance.Total} (${balance["Total ($)"]}$)\n`;
    });
    message += `Total: ${data.data[exchange].total}$\nAllocated: ${data.data[exchange].allocated_percentage}\n\n`;
  });

  return message;
}
