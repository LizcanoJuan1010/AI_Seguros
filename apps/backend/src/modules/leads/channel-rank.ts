import { Channel } from '../../generated/prisma/enums';

/**
 * Orden de progresión de canal para el motor de leads: click/interés (0) →
 * WhatsApp/email/web-chat (1) → llamada telefónica (2). Lo usan tanto el
 * ratchet de `Lead.highestChannel` (nunca retrocede) como las fórmulas de
 * `LeadScoringService` (bono de canal alcanzado, escalación).
 */
export const CHANNEL_RANK: Record<Channel, number> = {
  [Channel.WEB_INTEREST]: 0,
  [Channel.WHATSAPP]: 1,
  [Channel.EMAIL]: 1,
  [Channel.WEB_CHAT]: 1,
  [Channel.VOICE_CALL]: 2,
};

/** Mayor de dos canales por rango (o `b` si `a` es null/undefined). */
export function higherChannel(
  a: Channel | null | undefined,
  b: Channel,
): Channel {
  if (!a) return b;
  return CHANNEL_RANK[b] > CHANNEL_RANK[a] ? b : a;
}
