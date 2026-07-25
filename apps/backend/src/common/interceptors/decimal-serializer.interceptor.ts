import {
  CallHandler,
  ExecutionContext,
  Injectable,
  NestInterceptor,
  StreamableFile,
} from '@nestjs/common';
import { map, Observable } from 'rxjs';
import { Prisma } from '../../generated/prisma/client';

function serializeDecimals(value: unknown): unknown {
  if (value instanceof Prisma.Decimal) {
    return value.toFixed();
  }

  // No recorrer descargas binarias: convertir un StreamableFile en objeto
  // plano rompe el streaming (Nest deja de reconocerlo y lo serializa a JSON).
  if (value instanceof StreamableFile) {
    return value;
  }

  if (Array.isArray(value)) {
    return value.map(serializeDecimals);
  }

  if (value && typeof value === 'object' && !(value instanceof Date)) {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        key,
        serializeDecimals(item),
      ]),
    );
  }

  return value;
}

@Injectable()
export class DecimalSerializerInterceptor implements NestInterceptor {
  intercept(
    _context: ExecutionContext,
    next: CallHandler,
  ): Observable<unknown> {
    return next.handle().pipe(map(serializeDecimals));
  }
}
