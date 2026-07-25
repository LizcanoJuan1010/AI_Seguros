import {
  BadRequestException,
  Body,
  Controller,
  Delete,
  Get,
  HttpCode,
  HttpStatus,
  Param,
  Patch,
  Post,
  Query,
  StreamableFile,
  UploadedFiles,
  UseGuards,
  UseInterceptors,
} from '@nestjs/common';
import { FilesInterceptor } from '@nestjs/platform-express';
import { OptionalJwtAuthGuard } from '../../common/jwt-auth.guard';
import { UuidParamPipe } from '../../common/pipes/uuid-param.pipe';
import { TenantId } from '../../common/tenant.decorator';
import {
  CreateCustomerDto,
  QueryCustomersDto,
  UpdateCustomerDto,
} from './customers.dto';
import { CustomersService, type UploadedFileLike } from './customers.service';

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024; // 10 MB, igual que el chat

@UseGuards(OptionalJwtAuthGuard)
@Controller('customers')
export class CustomersController {
  constructor(private readonly service: CustomersService) {}

  @Post()
  create(@TenantId() tenantId: string, @Body() dto: CreateCustomerDto) {
    return this.service.create(tenantId, dto);
  }

  @Get()
  findAll(@TenantId() tenantId: string, @Query() query: QueryCustomersDto) {
    return this.service.findAll(tenantId, query);
  }

  // Cliente 360: TODO lo que el sistema sabe del cliente (perfil IA, datos
  // declarados, leads con historial, cotizaciones, pólizas, reclamos y
  // sesiones IA con transcripción). Lo consume el drawer de detalle del
  // vendedor. Declarada antes de ':id' por claridad de rutas.
  @Get(':id/full')
  findFull(
    @TenantId() tenantId: string,
    @Param('id', UuidParamPipe) id: string,
  ) {
    return this.service.findFull(tenantId, id);
  }

  // ---- Documentos adjuntos --------------------------------------------------
  // Las rutas con el literal 'documents' de dos+ segmentos no colisionan con
  // ':id' (un solo segmento). El binario se guarda en disco; la fila, en BD.

  @Post(':id/documents')
  @UseInterceptors(
    FilesInterceptor('files', 10, { limits: { fileSize: MAX_UPLOAD_BYTES } }),
  )
  uploadDocuments(
    @TenantId() tenantId: string,
    @Param('id', UuidParamPipe) id: string,
    @UploadedFiles() files: UploadedFileLike[],
    @Body('kind') kind?: string,
  ) {
    if (!files?.length) {
      throw new BadRequestException('No se recibió ningún archivo.');
    }
    return this.service.addDocuments(tenantId, id, files, kind);
  }

  @Get(':id/documents')
  listDocuments(
    @TenantId() tenantId: string,
    @Param('id', UuidParamPipe) id: string,
  ) {
    return this.service.listDocuments(tenantId, id);
  }

  @Get('documents/:docId/download')
  async downloadDocument(
    @TenantId() tenantId: string,
    @Param('docId', UuidParamPipe) docId: string,
  ): Promise<StreamableFile> {
    const { doc, stream } = await this.service.getDocumentStream(
      tenantId,
      docId,
    );
    // Las opciones de StreamableFile fijan los headers y Nest transmite el
    // binario (sin @Res, que rompía el streaming y serializaba el objeto).
    return new StreamableFile(stream, {
      type: doc.mimeType,
      disposition: `attachment; filename*=UTF-8''${encodeURIComponent(
        doc.filename,
      )}`,
    });
  }

  @Delete('documents/:docId')
  @HttpCode(HttpStatus.NO_CONTENT)
  async removeDocument(
    @TenantId() tenantId: string,
    @Param('docId', UuidParamPipe) docId: string,
  ): Promise<void> {
    await this.service.removeDocument(tenantId, docId);
  }

  @Get(':id')
  findOne(@TenantId() tenantId: string, @Param('id', UuidParamPipe) id: string) {
    return this.service.findOne(tenantId, id);
  }

  @Patch(':id')
  update(
    @TenantId() tenantId: string,
    @Param('id', UuidParamPipe) id: string,
    @Body() dto: UpdateCustomerDto,
  ) {
    return this.service.update(tenantId, id, dto);
  }

  @Delete(':id')
  @HttpCode(HttpStatus.NO_CONTENT)
  async remove(
    @TenantId() tenantId: string,
    @Param('id', UuidParamPipe) id: string,
  ): Promise<void> {
    await this.service.remove(tenantId, id);
  }
}
