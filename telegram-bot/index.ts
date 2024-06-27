import { exec, execSync } from 'child_process'
import 'dotenv/config'
import fs from 'fs'
import TelegramBot from 'node-telegram-bot-api'

const token = process.env.TELEGRAM_BOT_TOKEN || ''
const host = process.env.BROKER_HOST
const port = process.env.BROKER_PORT
const username = process.env.BROKER_USERNAME
const password = process.env.BROKER_PASSWORD

const threshold = parseFloat(process.env.BALANCE_THRESHOLD_IN_USD || '100')
const interval = parseInt(process.env.MONITORING_INTERVAL_IN_MINS || '30')
const monitoredBotIds = process.env.MONITORED_BOT_IDS ? process.env.MONITORED_BOT_IDS.split(',') : []

const chatId = process.env.TELEGRAM_ALERT_CHAT_ID || ''
const bot = new TelegramBot(token, { polling: true })

const commlibCliBaseCmd = `commlib-cli --host ${host} --port ${port} --username ${username} --password ${password} --btype mqtt`

interface BotInfo {
  id: string
  name: string
  accounts: string[]
}

interface BalanceData {
  Asset: string
  Total: number
  'Total ($)': number
}

interface StatusData {
  orders: OrderData[]
}

interface OrderData {
  Level: string
  Type: 'sell' | 'buy'
  Price: string
  Spread: string
  'Amount (Adj)': string
  'Quote (Adj)': string
  Age: string
}

interface ExchangeData {
  message?: string // "You have no balance on this exchange." (if no balance is available)
  balances?: BalanceData[]
  total?: string
  exchange?: string // Set by the code
}

interface BalanceResponse {
  status: number
  msg: string
  data: Record<string, ExchangeData>
}

type AccountName = string
type BotConfig = any

const BOTS_INFO_MAP = new Map<string, BotInfo>()

let JOYSTREAM_PRICE = 0

bot.on('polling_error', console.log)

// Check if commlib-cli is installed
try {
  execSync('commlib-cli --help', { stdio: 'ignore' })
} catch (error) {
  console.error(`commlib-cli is not installed. Exiting process. Error: ${error}`)
  process.exit(1)
}

// Read and parse bots-info.json file and populate the BOTS_INFO_MAP
try {
  const botsInfo: BotInfo[] = JSON.parse(fs.readFileSync(process.env.BOTS_INFO_FILE as string, 'utf8'))
  botsInfo.forEach((bot) => {
    BOTS_INFO_MAP.set(bot.id, bot)
  })
} catch (error) {
  console.error('Error reading or parsing bots-info.json:', error)
}

// Matches "/balance <bot-ID>"
bot.onText(/\/balance (\w+)/, async (msg, match) => {
  const chatId = msg.chat.id
  const botId = match ? match[1] : ''
  const balances = await getBalancesForAllBots([botId])
  const message = formatBalance(balances)
  bot.sendMessage(chatId, message || 'Error!', { parse_mode: 'Markdown' })
})

// Matches "/status <bot-ID>"
bot.onText(/\/status (\w+)?/, async (msg, match) => {
  const chatId = msg.chat.id
  const botId = match ? match[1] : ''
  const statuses = await getStatuses([botId])
  const message = formatStatuses(statuses)
  bot.sendMessage(chatId, message, { parse_mode: 'Markdown' })
})

// Matches "/status_all"
bot.onText(/\/status_all/, async (msg) => {
  const chatId = msg.chat.id
  const botIds = Array.from(BOTS_INFO_MAP.keys())
  const statuses = await getStatuses(botIds)
  const message = formatStatuses(statuses)
  bot.sendMessage(chatId, message || 'Error!', { parse_mode: 'Markdown' })
})

// Matches "/list"
bot.onText(/\/list/, (msg) => {
  const chatId = msg.chat.id
  const message = formatBotList()
  bot.sendMessage(chatId, message || 'Error!', { parse_mode: 'Markdown' })
})

// Matches "/balance_all"
bot.onText(/\/balance_all/, async (msg) => {
  const chatId = msg.chat.id
  const botIds = Array.from(BOTS_INFO_MAP.keys())
  const balances = await getBalancesForAllBots(botIds)
  const message = formatAllBalances(balances)
  bot.sendMessage(chatId, message || 'Error!', { parse_mode: 'Markdown' })
})

// Matches "/config <bot-ID>"
bot.onText(/\/config (\w+)?/, async (msg, match) => {
  const chatId = msg.chat.id
  const botId = match ? match[1] : ''
  const config = await getConfig(botId)
  const message = formatConfig(config)
  bot.sendMessage(chatId, message || 'Error!', { parse_mode: 'Markdown' })
})

// Matches "/config_all"
bot.onText(/\/config_all/, async (msg) => {
  const chatId = msg.chat.id
  const botIds = Array.from(BOTS_INFO_MAP.keys())
  const configs = await getConfigsForAllBots(botIds)
  const filteredConfigs = configs.filter((bot) => bot.config.strategy === 'pure_market_making')
  await sendConfigsInSeparateMessages(chatId, filteredConfigs)
})

// Function to send each configuration in a separate message
async function sendConfigsInSeparateMessages(
  chatId: number,
  configs: { botId: string; name: string | undefined; config: BotConfig }[]
) {
  for (const botConfig of configs) {
    const message = `Bot ID: *${botConfig.botId}*\nBot Name: *${botConfig.name}*\n${formatConfig(botConfig.config)}`
    await bot.sendMessage(chatId, message || 'No config found for this bot.', { parse_mode: 'Markdown' })
  }
}

// Function to execute the command and get the balance
async function getBalance(botId: string): Promise<BalanceResponse | undefined> {
  return new Promise((resolve) => {
    exec(`${commlibCliBaseCmd} rpcc 'hbot/${botId}/balance' {}`, { encoding: 'utf8' }, (error, stdout) => {
      if (error) {
        console.error('Error:', error)
        resolve(undefined)
      } else {
        try {
          const jsonString = stdout.replace(/'/g, '"')
          const data: BalanceResponse = JSON.parse(jsonString)

          // Remove the exchanges_total key
          delete data.data.exchanges_total

          Object.values(data.data).forEach((exchangeData) => {
            if (exchangeData.balances) {
              exchangeData.balances.forEach((balance) => {
                if (balance.Asset === 'JOY' || balance.Asset === 'JOYSTREAM') {
                  balance.Asset = 'JOY'
                  if (JOYSTREAM_PRICE) {
                    const newTotal = balance.Total * JOYSTREAM_PRICE
                    balance['Total ($)'] = parseFloat(newTotal.toFixed(1))
                  }
                }
              })
              exchangeData.total = exchangeData.balances
                .reduce((acc, balance) => acc + balance['Total ($)'], 0)
                .toFixed(1)
            }
          })

          resolve(data)
        } catch (parseError) {
          console.error('Parse Error:', parseError)
          resolve(undefined)
        }
      }
    })
  })
}

// Function to execute the command and get the balance by bot ID
async function getBalancesForAllBots(botIds: string[]): Promise<Record<AccountName, ExchangeData>> {
  const balances = await Promise.all(
    botIds.map(async (botId) => {
      const botBalance = await getBalance(botId)
      return { botId, botBalance }
    })
  )
  return aggregateBalancesByAccount(balances)
}

// Function to aggregate balances by account
function aggregateBalancesByAccount(
  botBalances: { botId: string; botBalance?: BalanceResponse }[]
): Record<AccountName, ExchangeData> {
  const accountBalances: Record<AccountName, ExchangeData> = {}

  botBalances.forEach(({ botId, botBalance }) => {
    const botInfo = BOTS_INFO_MAP.get(botId)
    if (botInfo) {
      botInfo.accounts.forEach((account) => {
        // Extract exchange name using account
        const exchange = getExchangeFromAccount(account)
        if (botBalance?.data && Object.keys(botBalance?.data).includes(exchange)) {
          botBalance.data[exchange].exchange = exchange
          accountBalances[account] = botBalance.data[exchange]
        }
      })
    }
  })

  return accountBalances
}

// Function to format balance data into a message
function formatBalance(data: Record<AccountName, ExchangeData>): string {
  let message = ''

  Object.keys(data).forEach((account) => {
    message += `Exchange: *${data[account].exchange}*\n`
    message += `Account: *${account}*\n`

    if (data[account].message) {
      message += `${data[account].message}\n\n`
      return
    }

    data[account].balances?.forEach((balance) => {
      message += `  *${balance.Asset}*: *${balance['Total ($)'].toFixed(1)}$* (${balance.Total.toFixed(1)})\n`
    })

    message += `Total: *${data[account].total}*$\n\n`
  })

  return message
}

function getExchangeFromAccount(account: string): string {
  const exchange = account.split('_')[0].toLowerCase()
  return exchange === 'gate' ? `${exchange}_io` : exchange
}

// Function to format all balances into a message
function formatAllBalances(data: Record<AccountName, ExchangeData>): string {
  let message = ''
  const assetSums: Record<string, { total: number; totalValue: number }> = {}

  const accounts = Object.keys(data).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }))
  accounts.forEach((account) => {
    message += `\nAccount: *${account}*\n`

    if (data[account].message) {
      message += `${data[account].message}\n\n`
      return
    }

    data[account].balances?.forEach((balance) => {
      if (balance.Asset == 'JOY' || balance.Asset == 'USDT' || balance.Asset == 'USDC') {
        message += `  *${balance.Asset}*: *${balance['Total ($)'].toFixed(1)}$* (${balance.Total.toFixed(1)})\n`

        if (!assetSums[balance.Asset]) {
          assetSums[balance.Asset] = { total: 0, totalValue: 0 }
        }
        assetSums[balance.Asset].total += balance.Total
        assetSums[balance.Asset].totalValue += balance['Total ($)']
      }
    })
  })

  message += `\n*Total:*\n`
  let totalValueSum = 0
  Object.keys(assetSums).forEach((asset) => {
    message += `*${asset}*: ${assetSums[asset].total.toFixed(2)} (${assetSums[asset].totalValue.toFixed(1)}$)\n`
    totalValueSum += assetSums[asset].totalValue
  })
  message += `\n*$$$*: ${totalValueSum.toFixed(1)}\n`

  return message
}

// Function to get statuses of specified bots from BOTS_INFO_MAP asynchronously
async function getStatuses(
  botIds: string[]
): Promise<{ botId: string; name: string | undefined; status: StatusData | string }[]> {
  const statuses = await Promise.all(
    botIds.map(async (botId) => {
      const botInfo = BOTS_INFO_MAP.get(botId)
      const status = await getStatus(botId)
      return { botId, name: botInfo?.name, status: status }
    })
  )
  return statuses
}

// Function to execute the command and get the status
async function getStatus(botId: string): Promise<StatusData | string> {
  return new Promise((resolve) => {
    exec(`${commlibCliBaseCmd} rpcc 'hbot/${botId}/status' {}`, {}, (error, stdout) => {
      if (error) {
        console.error('Error:', error)
        resolve(`\u{274C} Error!`)
      } else {
        try {
          const jsonString = stdout.replace(/'/g, '"')
          const data = JSON.parse(jsonString)
          if (typeof data.msg === 'string') {
            const status = data.msg || 'OK'
            resolve(`\u{2705} ${status}`)
          } else {
            resolve(data.msg)
          }
        } catch (parseError) {
          console.error('Parse Error:', parseError)
          resolve(`\u{274C} Error!`)
        }
      }
    })
  })
}

// Function to format all bot statuses into a message
function formatStatuses(data: { botId: string; name: string | undefined; status: StatusData | string }[]): string {
  let message = ''
  let buyLiquidity = 0
  let sellLiquidity = 0
  data.forEach((bot) => {
    message += `Bot ID: *${bot.botId}*\nBot Name: *${bot.name}*\n`
    if (typeof bot.status === 'string') {
      message += `Status: *${bot.status}*\n\n`
    } else {
      message += `Status: *\u{2705} OK*\n`

      if (typeof bot.status.orders === 'string') {
        message += `Liquidity: *${bot.status.orders}*\n\n`
        return
      }

      const buyOrders = bot.status.orders.filter((order) => order.Type === 'buy')
      const sellOrders = bot.status.orders.filter((order) => order.Type === 'sell')

      const buyQuoteSum = buyOrders.reduce((sum, order) => sum + parseFloat(order['Quote (Adj)']), 0)
      const sellQuoteSum = sellOrders.reduce((sum, order) => sum + parseFloat(order['Quote (Adj)']), 0)
      buyLiquidity += buyQuoteSum
      sellLiquidity += sellQuoteSum

      const buySpreadRange = getSpreadRange(buyOrders)
      const sellSpreadRange = getSpreadRange(sellOrders)

      message += `Liquidity:\n  *Buy*: _${buySpreadRange} ($${buyQuoteSum.toFixed(
        2
      )})_\n  *Sell*: _${sellSpreadRange} ($${sellQuoteSum.toFixed(2)})_\n\n`
    }
  })
  message += `*Total Liquidity*:\n  *Buy*: _$${buyLiquidity.toFixed(2)}_\n  *Sell*: _$${sellLiquidity.toFixed(
    2
  )}_\n  *Total*: _$${(buyLiquidity + sellLiquidity).toFixed(2)}_`
  return message
}

function getSpreadRange(orders: OrderData[]): string {
  if (orders.length === 0) return 'N/A'
  const spreads = orders.map((order) => parseFloat(order.Spread))
  const minSpread = Math.min(...spreads).toFixed(2)
  const maxSpread = Math.max(...spreads).toFixed(2)
  return `${minSpread}% - ${maxSpread}%`
}

// The rest of your code remains unchanged

// Function to format the bot list into a message
function formatBotList(): string {
  let message = ''
  BOTS_INFO_MAP.forEach((botInfo, botId) => {
    message += `Bot ID: *${botId}*\nBot Name: *${botInfo.name}*\nAccounts: *${botInfo.accounts.join(', ')}*\n\n`
  })
  return message
}

// Function to execute the command and get the status
async function getConfig(botId: string): Promise<BotConfig> {
  return new Promise((resolve) => {
    exec(`${commlibCliBaseCmd} rpcc 'hbot/${botId}/config' {}`, { encoding: 'utf8' }, (error, stdout) => {
      if (error) {
        console.error('Error:', error)
        resolve({})
      } else {
        try {
          const jsonString = stdout
            .replace(/'/g, '"')
            .replace(/None/g, 'null')
            .replace(/True/g, 'true')
            .replace(/False/g, 'false')
          const data = JSON.parse(jsonString)
          resolve(data.config.strategy)
        } catch (parseError) {
          console.error('Parse Error:', parseError)
          resolve({})
        }
      }
    })
  })
}

// Function to get configurations of specified bots from BOTS_INFO_MAP asynchronously
async function getConfigsForAllBots(
  botIds: string[]
): Promise<{ botId: string; name: string | undefined; config: BotConfig }[]> {
  const configs = await Promise.all(
    botIds.map(async (botId) => {
      const botInfo = BOTS_INFO_MAP.get(botId)
      const config = await getConfig(botId)
      return { botId, name: botInfo?.name, config: config }
    })
  )
  return configs
}

function formatConfig(config: BotConfig): string {
  let message = ''

  if (config['strategy'] === 'pure_market_making') {
    for (const key in config) {
      // Filter not needed keys
      delete config['minimum_spread']
      delete config['inventory_target_base_pct']
      delete config['custom_api_update_interval']
      delete config['hanging_orders_cancel_pct']

      // Filter out default values (-1/0/1/None) and boolean values to construct a clean message
      if (
        config[key] === -1 ||
        config[key] === 0 ||
        config[key] === 1 ||
        config[key] === null ||
        typeof config[key] === 'boolean'
      ) {
        continue
      }
      message += `${key.replace(/_/g, ' ')}: *${config[key]}*\n`
    }
  } else if (config['strategy'] === 'amm_arb') {
    for (const key in config) {
      message += `${key.replace(/_/g, ' ')}: *${config[key]}*\n`
    }
  }

  return message
}

// MEXC as price oracle
async function updateJoystreamPrice() {
  try {
    const response = await fetch('https://api.mexc.com/api/v3/ticker/24hr?symbol=JOYSTREAMUSDT')
    const data: any = await response.json()
    JOYSTREAM_PRICE = parseFloat(data.lastPrice)
  } catch (error) {
    console.error('Fetching JOYSTREAM price failed', error)
  }
}

setInterval(updateJoystreamPrice, 10 * 1000) // Update every 10 seconds

// Function to check balances periodically
async function checkBalances() {
  const botIds = monitoredBotIds.length ? monitoredBotIds : Array.from(BOTS_INFO_MAP.keys())
  console.log('Checking balances for bots:', botIds)
  const balances = await getBalancesForAllBots(botIds)

  Object.keys(balances).forEach((account) => {
    balances[account].balances?.forEach((balance) => {
      if (
        balance['Total ($)'] < threshold &&
        (balance.Asset === 'JOY' || balance.Asset === 'USDT' || balance.Asset === 'USDC')
      ) {
        bot.sendMessage(
          chatId,
          //eslint-disable-next-line
          `\u{2757} *${balance.Asset}* balance of account *${account}* is less than *$${threshold}*\. Current balance: *${balance.Total}(${balance['Total ($)']}$)*`,
          { parse_mode: 'Markdown' }
        )
      }
    })
  })
}

// Set an interval to check balances every x minutes
setInterval(checkBalances, interval * 60 * 1000)
