import { Injectable, Logger } from '@nestjs/common';

const DEFAULT_BASE_URL = 'https://sandbox-api.polar.sh/v1';
const TIMEOUT_MS = 15_000;

export type PolarCheckoutResult = {
  checkoutId: string;
  checkoutUrl: string;
};

/**
 * Cliente HTTP de Polar (sandbox por defecto). Único dueño del access token
 * en Nest — el servicio IA no llama a Polar directamente.
 */
@Injectable()
export class PolarClient {
  private readonly logger = new Logger(PolarClient.name);

  isConfigured(): boolean {
    return Boolean(process.env.POLAR_ACCESS_TOKEN?.trim());
  }

  baseUrl(): string {
    return (
      process.env.POLAR_BASE_URL?.trim() || DEFAULT_BASE_URL
    ).replace(/\/$/, '');
  }

  /**
   * Producto one-time (prima en COP) + checkout session.
   * Polar no permite montos libres en precios fijos: cada cobro crea su propio
   * producto hidden con metadata.reference para correlacionar el webhook.
   */
  async createCheckout(
    amountCop: number,
    concept: string,
    reference: string,
  ): Promise<PolarCheckoutResult> {
    const token = process.env.POLAR_ACCESS_TOKEN?.trim();
    if (!token) {
      throw new Error('POLAR_ACCESS_TOKEN no configurado');
    }

    let name = (concept || 'Prima seguro Tequendama').trim().slice(0, 64);
    if (name.length < 3) {
      name = `Pago ${reference}`;
    }

    const headers = {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    };
    const base = this.baseUrl();

    const prod = await this.fetchJson(`${base}/products/`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        name,
        recurring_interval: null,
        visibility: 'hidden',
        metadata: { reference },
        prices: [
          {
            amount_type: 'fixed',
            price_currency: 'cop',
            price_amount: Math.round(amountCop * 100),
          },
        ],
      }),
    });
    const productId = prod.id as string | undefined;
    if (!productId) {
      throw new Error('respuesta de Polar sin id de producto');
    }

    const checkoutBody: Record<string, unknown> = {
      products: [productId],
      metadata: { reference },
    };
    const successUrl = process.env.POLAR_SUCCESS_URL?.trim();
    if (successUrl) {
      checkoutBody.success_url = successUrl;
    }

    const checkout = await this.fetchJson(`${base}/checkouts/`, {
      method: 'POST',
      headers,
      body: JSON.stringify(checkoutBody),
    });
    const checkoutId = checkout.id as string | undefined;
    const checkoutUrl = checkout.url as string | undefined;
    if (!checkoutId || !checkoutUrl) {
      throw new Error('respuesta de Polar sin checkout');
    }
    return { checkoutId, checkoutUrl };
  }

  private async fetchJson(
    url: string,
    init: RequestInit,
  ): Promise<Record<string, unknown>> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
    try {
      const resp = await fetch(url, { ...init, signal: controller.signal });
      const text = await resp.text();
      let data: Record<string, unknown> = {};
      try {
        data = text ? (JSON.parse(text) as Record<string, unknown>) : {};
      } catch {
        data = {};
      }
      if (!resp.ok) {
        this.logger.warn(`Polar ${init.method} ${url} → ${resp.status}: ${text.slice(0, 200)}`);
        throw new Error(`Polar HTTP ${resp.status}`);
      }
      return data;
    } finally {
      clearTimeout(timer);
    }
  }
}
