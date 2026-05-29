from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from inventario.services import recalcular_stock_producto


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
