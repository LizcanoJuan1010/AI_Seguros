import { Injectable, ParseUUIDPipe } from '@nestjs/common';

@Injectable()
export class UuidParamPipe extends ParseUUIDPipe {
  constructor() {
    super({ version: '4' });
  }
}
