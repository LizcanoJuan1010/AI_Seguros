import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { App } from 'supertest/types';
import { AppModule } from './../src/app.module';
import { configureApp } from './../src/app.setup';
import { PrismaService } from './../src/prisma/prisma.service';

interface CustomerBody {
  id: string;
  fullName: string | null;
  documentId: string | null;
  consentAt: string | null;
}

interface CustomerListBody {
  data: CustomerBody[];
  meta: { total: number };
}

describe('AppController (e2e)', () => {
  let app: INestApplication<App>;
  const databaseIt = process.env.RUN_DATABASE_E2E === 'true' ? it : it.skip;

  beforeAll(() => {
    process.env.DATABASE_URL ??=
      'postgresql://user:password@localhost:5432/tequendama_test';
  });

  beforeEach(async () => {
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleFixture.createNestApplication();
    configureApp(app);
    await app.init();
  });

  it('/api/v1 (GET)', () => {
    return request(app.getHttpServer())
      .get('/api/v1')
      .expect(200)
      .expect('Hello World!');
  });

  it('rechaza payloads inválidos antes de consultar la base', () => {
    return request(app.getHttpServer())
      .post('/api/v1/products')
      .send({})
      .expect(400);
  });

  it('rechaza identificadores que no son UUID', () => {
    return request(app.getHttpServer())
      .get('/api/v1/customers/no-es-un-uuid')
      .expect(400);
  });

  databaseIt('ejecuta el ciclo CRUD completo de clientes', async () => {
    await app.get(PrismaService).customer.count();
    const documentId = `E2E-${Date.now()}`;
    const created = await request(app.getHttpServer())
      .post('/api/v1/customers')
      .send({
        fullName: 'Cliente E2E',
        documentType: 'CC',
        documentId,
        consentData: true,
      })
      .expect(201);

    const id = (created.body as CustomerBody).id;

    const found = await request(app.getHttpServer())
      .get(`/api/v1/customers/${id}`)
      .expect(200);
    expect((found.body as CustomerBody).documentId).toBe(documentId);
    expect((found.body as CustomerBody).consentAt).toBeTruthy();

    const list = await request(app.getHttpServer())
      .get(`/api/v1/customers?documentId=${documentId}`)
      .expect(200);
    expect((list.body as CustomerListBody).meta.total).toBe(1);
    expect((list.body as CustomerListBody).data).toHaveLength(1);

    const updated = await request(app.getHttpServer())
      .patch(`/api/v1/customers/${id}`)
      .send({ fullName: 'Cliente E2E Actualizado' })
      .expect(200);
    expect((updated.body as CustomerBody).fullName).toBe(
      'Cliente E2E Actualizado',
    );

    await request(app.getHttpServer())
      .delete(`/api/v1/customers/${id}`)
      .expect(204);

    await request(app.getHttpServer())
      .get(`/api/v1/customers/${id}`)
      .expect(404);
  });

  afterEach(async () => {
    await app.close();
  });
});
