from django.urls import include, path
from rest_framework.routers import DefaultRouter

from inventario.views import (
    AjusteMermaViewSet,
    CategoriaViewSet,
    LoteViewSet,
    NotaDespachoViewSet,
    OrdenCompraViewSet,
    ProductoViewSet,
    UnidadMedidaViewSet,
    dashboard_resumen,
    reporte_consumo_semanal,
    reporte_top_mermas,
)

router = DefaultRouter()
router.register('categorias', CategoriaViewSet, basename='categoria')
router.register('unidades-medida', UnidadMedidaViewSet, basename='unidad-medida')
router.register('productos', ProductoViewSet, basename='producto')
router.register('ordenes-compra', OrdenCompraViewSet, basename='orden-compra')
router.register('lotes', LoteViewSet, basename='lote')
router.register('despachos', NotaDespachoViewSet, basename='despacho')
router.register('mermas', AjusteMermaViewSet, basename='merma')

urlpatterns = [
    path('', include(router.urls)),
    path('dashboard/resumen/', dashboard_resumen, name='dashboard-resumen'),
    path('reportes/consumo-semanal/', reporte_consumo_semanal, name='reporte-consumo-semanal'),
    path('reportes/top-mermas/', reporte_top_mermas, name='reporte-top-mermas'),
]
