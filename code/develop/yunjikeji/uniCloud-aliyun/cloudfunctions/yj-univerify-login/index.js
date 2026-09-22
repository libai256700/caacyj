'use strict'

const crypto = require('crypto')
const createConfig = require('uni-config-center')

const readRuntimeConfig = () => {
  const config = createConfig({ pluginId: 'yj-univerify' }).config() || {}
  const univerify = config.univerify && typeof config.univerify === 'object'
    ? config.univerify
    : config

  return {
    appId: typeof univerify.appId === 'string' && univerify.appId.trim()
      ? univerify.appId.trim()
      : '__UNI__F4DBB06',
    backendBaseUrl: typeof univerify.backendBaseUrl === 'string'
      ? univerify.backendBaseUrl.trim().replace(/\/+$/, '')
      : '',
    hmacSecret: typeof univerify.hmacSecret === 'string' ? univerify.hmacSecret.trim() : ''
  }
}

const readJson = (value) => {
  if (Buffer.isBuffer(value)) {
    return JSON.parse(value.toString('utf8'))
  }
  if (typeof value === 'string') {
    return JSON.parse(value)
  }
  return value
}

const sign = (secret, timestamp, mobile, role) => crypto
  .createHmac('sha256', secret)
  .update(`${timestamp}\n${mobile}\n${role}`, 'utf8')
  .digest('base64')
  .replace(/\+/g, '-')
  .replace(/\//g, '_')
  .replace(/=+$/, '')

exports.main = async (event, context) => {
  const runtimeConfig = readRuntimeConfig()
  const accessToken = typeof event?.accessToken === 'string' ? event.accessToken.trim() : ''
  const openid = typeof event?.openid === 'string' ? event.openid.trim() : ''
  const role = event?.role === 'enterprise' ? 'enterprise' : event?.role === 'student' ? 'student' : ''

  if (!accessToken || !openid || !role) {
    throw new Error('一键登录授权信息不完整')
  }
  if (!runtimeConfig.backendBaseUrl || !runtimeConfig.hmacSecret) {
    throw new Error('一键登录服务尚未配置')
  }

  const phoneResult = await uniCloud.getPhoneNumber({
    appid: context?.APPID || runtimeConfig.appId,
    provider: 'univerify',
    access_token: accessToken,
    openid
  })
  const mobile = typeof phoneResult?.phoneNumber === 'string' ? phoneResult.phoneNumber.trim() : ''
  if (!/^1\d{10}$/.test(mobile)) {
    throw new Error('未能获取有效手机号，请使用短信登录')
  }

  const timestamp = `${Date.now()}`
  const path = role === 'enterprise'
    ? '/app-api/yj/company-auth/univerify-login'
    : '/app-api/yj/customer-auth/univerify-login'
  const response = await uniCloud.httpclient.request(`${runtimeConfig.backendBaseUrl}${path}`, {
    method: 'POST',
    contentType: 'json',
    dataType: 'json',
    data: { mobile },
    headers: {
      'X-Yj-Univerify-Timestamp': timestamp,
      'X-Yj-Univerify-Signature': sign(runtimeConfig.hmacSecret, timestamp, mobile, role)
    }
  })
  const body = readJson(response.data)
  const session = body?.data !== undefined ? body.data : body?.result
  const success = response.status >= 200 && response.status < 300 &&
    (body?.code === 0 || body?.code === '0' || body?.success === true) && session
  if (!success) {
    throw new Error(body?.msg || body?.message || '账号服务暂不可用，请使用短信登录')
  }

  return { role, session }
}
