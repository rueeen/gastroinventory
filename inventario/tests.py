from contextlib import nullcontext
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework import serializers

from inventario.models import NotaDespacho, OrdenCompra
from inventario.serializers import OrdenCompraSerializer
from inventario.services import procesar_despacho_fifo, recalcular_stock_producto
from inventario.signals import (
    crear_lotes_al_recibir_orden,
    descontar_stock_al_despachar,
)


class RecalcularStockProductoTests(SimpleTestCase):
    def test_usa_save_con_update_fields_para_generar_historial(self):
        producto = SimpleNamespace(pk=1, stock_actual=Decimal('0.000'))
        lote_manager = MagicMock()
        lote_manager.filter.return_value.aggregate.return_value = {'total': Decimal('5.000')}

        with patch('inventario.models.Lote.objects', lote_manager):
            producto.save = MagicMock()

            total = recalcular_stock_producto(producto)

        self.assertEqual(total, Decimal('5.000'))
        self.assertEqual(producto.stock_actual, Decimal('5.000'))
        producto.save.assert_called_once_with(update_fields=['stock_actual'])
        lote_manager.filter.assert_called_once_with(producto=producto, activo=True)


class ProcesarDespachoFifoTests(SimpleTestCase):
    def test_retorna_lista_vacia_si_descuento_fifo_falla_por_value_error(self):
        estado = SimpleNamespace(DESPACHADO='DESPACHADO')

        class Despacho:
            objects = MagicMock()

        Despacho.Estado = estado

        detalle = SimpleNamespace(
            pk=5,
            producto=SimpleNamespace(nombre='Harina'),
            cantidad=Decimal('10.000'),
        )
        despacho = Despacho()
        despacho.pk = 7
        despacho.estado = estado.DESPACHADO
        despacho.creado_por = SimpleNamespace(pk=1)
        despacho.detalles = MagicMock()
        despacho.detalles.all.return_value = [detalle]

        Despacho.objects.select_for_update.return_value = Despacho.objects
        Despacho.objects.prefetch_related.return_value = Despacho.objects
        Despacho.objects.get.return_value = despacho
        movimiento_manager = MagicMock()
        movimiento_manager.filter.return_value.exists.return_value = False

        with (
            patch('inventario.models.MovimientoLote.objects', movimiento_manager),
            patch(
                'inventario.services.ContentType.objects.get_for_model',
                return_value=SimpleNamespace(pk=1),
            ),
            patch(
                'inventario.services.descontar_stock_fifo',
                side_effect=ValueError('Stock insuficiente'),
            ),
            patch('inventario.services.transaction.atomic', return_value=nullcontext()),
            self.assertLogs('inventario.services', level='ERROR'),
        ):
            movimientos = procesar_despacho_fifo(despacho)

        self.assertEqual(movimientos, [])


class OrdenCompraSerializerTests(SimpleTestCase):
    def test_validate_detalles_rechaza_productos_duplicados(self):
        producto = SimpleNamespace(pk=1, nombre='Tomate')
        serializer = OrdenCompraSerializer()

        with self.assertRaises(serializers.ValidationError) as context:
            serializer.validate_detalles([
                {
                    'producto': producto,
                    'cantidad': Decimal('1.000'),
                    'precio_unitario': Decimal('100.00'),
                },
                {
                    'producto': producto,
                    'cantidad': Decimal('2.000'),
                    'precio_unitario': Decimal('100.00'),
                },
            ])

        self.assertIn('No puede repetir productos', str(context.exception))
        self.assertIn('Tomate', str(context.exception))


class SignalOnCommitTests(SimpleTestCase):
    def test_creacion_lotes_usa_on_commit_robusto(self):
        orden = SimpleNamespace(
            estado=OrdenCompra.Estado.RECIBIDA,
            _estado_anterior=OrdenCompra.Estado.BORRADOR,
        )

        with patch('inventario.signals.transaction.on_commit') as on_commit:
            crear_lotes_al_recibir_orden(OrdenCompra, orden, created=False)

        on_commit.assert_called_once()
        self.assertIs(on_commit.call_args.kwargs['robust'], True)

    def test_descuento_fifo_usa_on_commit_robusto(self):
        despacho = SimpleNamespace(
            estado=NotaDespacho.Estado.DESPACHADO,
            _estado_anterior=NotaDespacho.Estado.BORRADOR,
        )

        with patch('inventario.signals.transaction.on_commit') as on_commit:
            descontar_stock_al_despachar(NotaDespacho, despacho, created=False)

        on_commit.assert_called_once()
        self.assertIs(on_commit.call_args.kwargs['robust'], True)
