from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Sum
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML


def generar_numero_documento(tipo: str) -> str:
    from inventario.models import SecuenciaDocumento

    anio = timezone.localdate().year
    with transaction.atomic():
        secuencia, _ = SecuenciaDocumento.objects.select_for_update().get_or_create(
            tipo=tipo,
            anio=anio,
            defaults={'ultimo_numero': 0},
        )
        secuencia.ultimo_numero += 1
        secuencia.save(update_fields=['ultimo_numero'])
    return f'{tipo}-{anio}-{secuencia.ultimo_numero:04d}'


def generar_numero_oc() -> str:
    return generar_numero_documento('OC')


def generar_numero_nd() -> str:
    return generar_numero_documento('ND')


def recalcular_stock_producto(producto):
    from inventario.models import Lote

    total = Lote.objects.filter(producto=producto, activo=True).aggregate(
        total=Sum('cantidad_disponible'),
    )['total'] or Decimal('0.000')
    producto.stock_actual = total
    producto.save(update_fields=['stock_actual'])
    return total


def descontar_stock_fifo(producto, cantidad: Decimal, tipo: str, registrado_por, referencia_obj=None):
    from inventario.models import Lote, MovimientoLote

    cantidad = Decimal(cantidad)
    if cantidad <= 0:
        raise ValueError('La cantidad a descontar debe ser mayor que cero.')

    movimientos = []
    restante = cantidad

    with transaction.atomic():
        lotes = (
            Lote.objects.select_for_update()
            .filter(producto=producto, activo=True, cantidad_disponible__gt=0)
            .order_by('fecha_ingreso', 'id')
        )
        disponible = sum((lote.cantidad_disponible for lote in lotes), Decimal('0.000'))
        if disponible < cantidad:
            raise ValueError(f'Stock insuficiente para {producto.nombre}. Disponible: {disponible}, requerido: {cantidad}.')

        content_type = None
        object_id = None
        if referencia_obj is not None:
            content_type = ContentType.objects.get_for_model(referencia_obj, for_concrete_model=False)
            object_id = referencia_obj.pk

        for lote in lotes:
            if restante <= 0:
                break
            descuento = min(lote.cantidad_disponible, restante)
            lote.cantidad_disponible -= descuento
            lote.activo = lote.cantidad_disponible > 0
            lote.save(update_fields=['cantidad_disponible', 'activo'])
            movimiento = MovimientoLote.objects.create(
                lote=lote,
                tipo=tipo,
                cantidad=descuento,
                content_type=content_type,
                object_id=object_id,
                registrado_por=registrado_por,
            )
            movimientos.append(movimiento)
            restante -= descuento

        recalcular_stock_producto(producto)

    return movimientos


def crear_lotes_desde_orden(orden):
    from inventario.models import Lote

    lotes = []
    with transaction.atomic():
        orden = orden.__class__.objects.select_for_update().prefetch_related('detalles__producto').get(pk=orden.pk)
        if orden.estado != orden.Estado.RECIBIDA:
            return lotes
        if not orden.detalles.exists():
            return lotes
        for detalle in orden.detalles.all():
            if Lote.objects.filter(orden_compra=orden, producto=detalle.producto).exists():
                continue
            lotes.append(
                Lote.objects.create(
                    producto=detalle.producto,
                    orden_compra=orden,
                    cantidad_inicial=detalle.cantidad,
                    cantidad_disponible=detalle.cantidad,
                    fecha_ingreso=orden.fecha,
                    activo=True,
                )
            )
    return lotes


def procesar_despacho_fifo(despacho):
    from inventario.models import MovimientoLote

    movimientos = []
    with transaction.atomic():
        despacho = despacho.__class__.objects.select_for_update().prefetch_related('detalles__producto').get(pk=despacho.pk)
        if despacho.estado != despacho.Estado.DESPACHADO:
            return movimientos
        for detalle in despacho.detalles.all():
            if MovimientoLote.objects.filter(
                content_type=ContentType.objects.get_for_model(detalle, for_concrete_model=False),
                object_id=detalle.pk,
            ).exists():
                continue
            movimientos.extend(
                descontar_stock_fifo(
                    producto=detalle.producto,
                    cantidad=detalle.cantidad,
                    tipo=MovimientoLote.Tipo.DESPACHO,
                    registrado_por=despacho.creado_por,
                    referencia_obj=detalle,
                )
            )
    return movimientos


def procesar_merma_fifo(merma):
    from inventario.models import MovimientoLote

    content_type = ContentType.objects.get_for_model(merma, for_concrete_model=False)
    if MovimientoLote.objects.filter(content_type=content_type, object_id=merma.pk).exists():
        return []
    return descontar_stock_fifo(
        producto=merma.producto,
        cantidad=merma.cantidad,
        tipo=MovimientoLote.Tipo.MERMA,
        registrado_por=merma.registrado_por,
        referencia_obj=merma,
    )


def generar_pdf(template_name, context):
    html_string = render_to_string(template_name, context)
    return HTML(string=html_string).write_pdf()
