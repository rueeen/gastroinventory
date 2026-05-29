from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from inventario.models import AjusteMerma, Lote, NotaDespacho, OrdenCompra
from inventario.services import crear_lotes_desde_orden, procesar_despacho_fifo, procesar_merma_fifo, recalcular_stock_producto


@receiver(pre_save, sender=OrdenCompra)
def recordar_estado_anterior_orden(sender, instance, **kwargs):
    if instance.pk:
        instance._estado_anterior = sender.objects.filter(pk=instance.pk).values_list('estado', flat=True).first()
    else:
        instance._estado_anterior = None


@receiver(post_save, sender=OrdenCompra)
def crear_lotes_al_recibir_orden(sender, instance, created, **kwargs):
    estado_anterior = getattr(instance, '_estado_anterior', None)
    if instance.estado == OrdenCompra.Estado.RECIBIDA and estado_anterior != OrdenCompra.Estado.RECIBIDA:
        transaction.on_commit(lambda: crear_lotes_desde_orden(instance))


@receiver(pre_save, sender=NotaDespacho)
def recordar_estado_anterior_despacho(sender, instance, **kwargs):
    if instance.pk:
        instance._estado_anterior = sender.objects.filter(pk=instance.pk).values_list('estado', flat=True).first()
    else:
        instance._estado_anterior = None


@receiver(post_save, sender=NotaDespacho)
def descontar_stock_al_despachar(sender, instance, created, **kwargs):
    estado_anterior = getattr(instance, '_estado_anterior', None)
    if instance.estado == NotaDespacho.Estado.DESPACHADO and estado_anterior != NotaDespacho.Estado.DESPACHADO:
        transaction.on_commit(lambda: procesar_despacho_fifo(instance))


@receiver(post_save, sender=AjusteMerma)
def descontar_stock_al_registrar_merma(sender, instance, created, **kwargs):
    if created:
        procesar_merma_fifo(instance)


@receiver(post_save, sender=Lote)
def recalcular_stock_al_guardar_lote(sender, instance, **kwargs):
    recalcular_stock_producto(instance.producto)


@receiver(post_delete, sender=Lote)
def recalcular_stock_al_eliminar_lote(sender, instance, **kwargs):
    recalcular_stock_producto(instance.producto)
