import {
  ArgumentsHost,
  Catch,
  ConflictException,
  ExceptionFilter,
  HttpStatus,
  NotFoundException,
} from '@nestjs/common';
import type { Response } from 'express';
import { Prisma } from '../../generated/prisma/client';

@Catch(Prisma.PrismaClientKnownRequestError)
export class PrismaExceptionFilter implements ExceptionFilter {
  catch(
    exception: Prisma.PrismaClientKnownRequestError,
    host: ArgumentsHost,
  ): void {
    const response = host.switchToHttp().getResponse<Response>();

    if (exception.code === 'P2025') {
      const error = new NotFoundException('El registro solicitado no existe');
      response.status(error.getStatus()).json(error.getResponse());
      return;
    }

    if (exception.code === 'P2002') {
      const error = new ConflictException(
        'Ya existe un registro con esos datos',
      );
      response.status(error.getStatus()).json(error.getResponse());
      return;
    }

    if (exception.code === 'P2003') {
      const error = new ConflictException(
        'La operación viola una relación entre registros',
      );
      response.status(error.getStatus()).json(error.getResponse());
      return;
    }

    response.status(HttpStatus.INTERNAL_SERVER_ERROR).json({
      statusCode: HttpStatus.INTERNAL_SERVER_ERROR,
      message: 'Error interno de persistencia',
    });
  }
}
