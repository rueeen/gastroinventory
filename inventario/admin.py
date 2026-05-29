from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from inventario.models import (
    AjusteMerma,
    Categoria,
    DetalleDespacho,
    DetalleOrdenCompra,
    Lote,
    MovimientoLote,
    NotaDespacho,
    OrdenCompra,
    Producto,
    SecuenciaDocumento,
    UnidadMedida,
)


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'descripcion']
    search_fields = ['nombre']


@admin.register(UnidadMedida)
class UnidadMedidaAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'abreviatura']
    search_fields = ['nombre', 'abreviatura']


@admin.register(Producto)
class ProductoAdmin(SimpleHistoryAdmin):
    list_display = ['nombre', 'categoria', 'unidad_medida', 'stock_actual', 'stock_minimo', 'activo']
    list_filter = ['categoria', 'activo']
    search_fields = ['nombre']
    readonly_fields = ['stock_actual', 'creado_en']


class DetalleOrdenCompraInline(admin.TabularInline):
    model = DetalleOrdenCompra
    extra = 1


@admin.register(OrdenCompra)
class OrdenCompraAdmin(SimpleHistoryAdmin):
    list_display = ['numero', 'proveedor', 'fecha', 'estado', 'creado_por', 'creado_en']
    list_filter = ['estado', 'fecha']
    search_fields = ['numero', 'proveedor']
    readonly_fields = ['numero', 'creado_en']
    inlines = [DetalleOrdenCompraInline]


@admin.register(Lote)
class LoteAdmin(SimpleHistoryAdmin):
    list_display = ['id', 'producto', 'orden_compra', 'cantidad_inicial', 'cantidad_disponible', 'fecha_ingreso', 'fecha_vencimiento', 'activo']
    list_filter = ['activo', 'fecha_ingreso', 'fecha_vencimiento']
    search_fields = ['producto__nombre', 'orden_compra__numero']


class DetalleDespachoInline(admin.TabularInline):
    model = DetalleDespacho
    extra = 1


@admin.register(NotaDespacho)
class NotaDespachoAdmin(SimpleHistoryAdmin):
    list_display = ['numero', 'fecha', 'clase', 'docente', 'num_alumnos', 'estado', 'creado_por']
    list_filter = ['estado', 'fecha']
    search_fields = ['numero', 'clase', 'docente']
    readonly_fields = ['numero']
    inlines = [DetalleDespachoInline]


@admin.register(MovimientoLote)
class MovimientoLoteAdmin(admin.ModelAdmin):
    list_display = ['id', 'lote', 'tipo', 'cantidad', 'fecha', 'registrado_por']
    list_filter = ['tipo', 'fecha']
    search_fields = ['lote__producto__nombre']
    readonly_fields = ['fecha']


@admin.register(AjusteMerma)
class AjusteMermaAdmin(SimpleHistoryAdmin):
    list_display = ['producto', 'cantidad', 'motivo', 'fecha', 'registrado_por']
    list_filter = ['motivo', 'fecha']
    search_fields = ['producto__nombre', 'detalle']


@admin.register(SecuenciaDocumento)
class SecuenciaDocumentoAdmin(admin.ModelAdmin):
    list_display = ['tipo', 'anio', 'ultimo_numero']
    list_filter = ['tipo', 'anio']
