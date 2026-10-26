# Research notes (sources for the report)

## The problem
- FTC: Americans reported $15.9B in fraud losses in 2025; investment scams were the #1 category by losses,
  over $7.9B, average individual loss over $10,000 (up from $5.7B in 2024). Older adults: $1.059B in investment
  scams, +42% in a year, often first contacted on social media.
  - https://www.ftc.gov/news-events/news/press-releases/2026/03/ftc-testifies-joint-economic-committee-agencys-efforts-combat-fraud
  - https://www.ftc.gov/system/files/ftc_gov/pdf/ftc-testimony-jec-hearing-on-the-rising-scam-economy.pdf
- FINRA Foundation (National Financial Capability Study, 2024 data): 26% of investors use finfluencer
  recommendations; about 61% of investors under 35. Social-media users answered 42% of investment-knowledge
  questions correctly but 63% rated their knowledge high. Among those targeted for fraud, 68% of social media users
  lost money vs 29% of non-users.
  - https://www.finra.org/media-center/newsreleases/2025/new-finra-foundation-research-examines-shifting-investor-behaviors
  - https://finance.yahoo.com/markets/stocks/article/young-investors-tap-social-media-for-investing-advice-with-mixed-results-204433279.html

## What already exists
- Robinhood Cortex: AI research assistant for Robinhood Gold members (~$5/mo); summarizes what's moving a stock.
  Only inside Robinhood. https://www.benzinga.com/25/03/44530226/robinhood-launches-ai-investment-tool-cortex-to-expand-market-analysis-access-a-premium-research-assistant-right-
- Public.com Alpha: broker AI that explains what's moving a stock. https://walnutinvest.com/resources/which-brokers-have-an-ai-assistant
- Perplexity Finance: cited research, quotes, analyst consensus, SEC filing links; free + Pro $20/mo.
  https://gptprompts.ai/how-to-use-perplexity-for-stock-research
- ChatGPT / general chatbots: answer anything, but mix remembered numbers with live ones, and can be steered by
  text pasted into them (prompt injection).
- Yahoo Finance, Seeking Alpha, Morningstar: data and analyst opinion, but the user must know what to look up.

## What's different about TipCheck
- Starts from the *tip* (the thing people actually receive), not from a ticker or a question.
- Breaks a tip into claims and gives each claim a verdict (supported / partly / contradicted / can't verify).
- Adversarial bull-vs-bear design so the output is balanced by construction.
- Every number is checked in code against fetched evidence; made-up numbers are removed and shown.
- Treats the tip as hostile input: scam pressure tactics and prompt injection are flagged as red flags.
- Never says buy/sell (filtered in code), so it is an education/fraud-prevention tool, not an adviser.
