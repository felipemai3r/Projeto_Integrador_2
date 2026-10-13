import { describe, expect, it } from 'vitest'
import { chaveParaBytes, ehIphone, iphoneSemInstalar, suportaPush } from './push'

describe('push', () => {
  it('converte a chave publica VAPID (base64url) em bytes', () => {
    // "AQID" em base64url = bytes 1, 2, 3
    expect(Array.from(chaveParaBytes('AQID'))).toEqual([1, 2, 3])
    // sem preenchimento e com caracteres de URL
    expect(Array.from(chaveParaBytes('-_8'))).toEqual([251, 255])
  })

  it('a chave VAPID real tem 65 bytes e comeca com 0x04 (ponto nao comprimido)', () => {
    const chave =
      'BLIpde7ENXoa9nHfCSFB5fIYMB6N3PgOY5odqR3SXLv_iiXcW74ZOApQTmqb1LV08QRgOOhzBmM8n9nR7lzJzvk'
    const bytes = chaveParaBytes(chave)
    expect(bytes[0]).toBe(4)
    expect(bytes.length).toBeGreaterThan(60)
  })

  it('no iPhone so ha push com o app instalado na tela inicial', () => {
    const iphone = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15'
    const mac = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
    expect(ehIphone(iphone)).toBe(true)
    expect(ehIphone(mac)).toBe(false)
    expect(iphoneSemInstalar(iphone, false)).toBe(true)
    expect(iphoneSemInstalar(iphone, true)).toBe(false)
    expect(iphoneSemInstalar(mac, false)).toBe(false)
  })

  it('detecta falta de suporte a push', () => {
    expect(suportaPush({ navigator: {} as Navigator })).toBe(false)
  })
})
