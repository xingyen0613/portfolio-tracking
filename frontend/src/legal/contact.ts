export const SUPPORT_EMAIL = 'xingyen0613@gmail.com'
export const SUPPORT_TELEGRAM = 'xingyen0613'
export const SUPPORT_TELEGRAM_URL = `https://t.me/${SUPPORT_TELEGRAM}`

export const REFUND_REQUEST_URL =
  `mailto:${SUPPORT_EMAIL}` +
  '?subject=' + encodeURIComponent('[ALL IN] 退款申請') +
  '&body=' + encodeURIComponent(
    [
      '請填寫以下資訊，以便我們核對扣款紀錄：',
      '',
      '訂閱使用的登入帳號 email：',
      '扣款日期：',
      '扣款金額：',
      '交易或訂單編號（若有）：',
      '退款事由：',
    ].join('\n'),
  )
