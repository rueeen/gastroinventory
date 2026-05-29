from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MinValueValidator
from django.db import models
from simple_history.models import HistoricalRecords

User = get_user_model()


class Categoria(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = 'categoría'
        verbose_name_plural = 'categorías'

    def __str__(self):
        return self.nombre


class UnidadMedida(models.Model):
    nombre = models.CharField(max_length=50)
    abreviatura = models.CharField(max_length=10)

    class Meta:
        ordering = ['nombre']
        verbose_name = 'unidad de medida'
        verbose_name_plural = 'unidades de medida'
        constraints = [
            models.UniqueConstraint(fields=['nombre', 'abreviatura'], name='unidad_medida_nombre_abreviatura_unica'),
        ]

    def __str__(self):
        return f'{self.nombre} ({self.abreviatura})'


class Producto(models.Model):
    nombre = models.CharField(max_length=200)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name='productos')
    unidad_medida = models.ForeignKey(UnidadMedida, on_delete=models.PROTECT, related_name='productos')
    stock_actual = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal('0.000'))
    stock_minimo = models.DecimalField(max_digits=10, decimal_places=3, validators=[MinValueValidator(Decimal('0.000'))])
    peso_unitario_ref = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class OrdenCompra(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = 'BORRADOR', 'Borrador'
        RECIBIDA = 'RECIBIDA', 'Recibida'
        ANULADA = 'ANULADA', 'Anulada'

    numero = models.CharField(max_length=20, unique=True, blank=True)
    proveedor = models.CharField(max_length=200)
    fecha = models.DateField()
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.BORRADOR)
    creado_por = models.ForeignKey(User, on_delete=models.PROTECT, related_name='ordenes_compra')
    observaciones = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ['-fecha', '-id']
        verbose_name = 'orden de compra'
        verbose_name_plural = 'órdenes de compra'

    def save(self, *args, **kwargs):
        if not self.numero:
            from inventario.services import generar_numero_oc

            self.numero = generar_numero_oc()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.numero or f'Orden de compra {self.pk}'


class DetalleOrdenCompra(models.Model):
    orden = models.ForeignKey(OrdenCompra, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name='detalles_compra')
    cantidad = models.DecimalField(max_digits=10, decimal_places=3, validators=[MinValueValidator(Decimal('0.001'))])
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))])

    class Meta:
        verbose_name = 'detalle de orden de compra'
        verbose_name_plural = 'detalles de órdenes de compra'

    def __str__(self):
        return f'{self.producto} x {self.cantidad}'


class Lote(models.Model):
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name='lotes')
    orden_compra = models.ForeignKey(OrdenCompra, on_delete=models.SET_NULL, null=True, blank=True, related_name='lotes')
    cantidad_inicial = models.DecimalField(max_digits=10, decimal_places=3, validators=[MinValueValidator(Decimal('0.001'))])
    cantidad_disponible = models.DecimalField(max_digits=10, decimal_places=3, validators=[MinValueValidator(Decimal('0.000'))])
    fecha_ingreso = models.DateField()
    fecha_vencimiento = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ['fecha_ingreso', 'id']

    def __str__(self):
        return f'Lote {self.pk} - {self.producto}'


class NotaDespacho(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = 'BORRADOR', 'Borrador'
        DESPACHADO = 'DESPACHADO', 'Despachado'
        ANULADO = 'ANULADO', 'Anulado'

    numero = models.CharField(max_length=20, unique=True, blank=True)
    fecha = models.DateField()
    clase = models.CharField(max_length=200)
    docente = models.CharField(max_length=200)
    num_alumnos = models.IntegerField(validators=[MinValueValidator(1)])
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.BORRADOR)
    creado_por = models.ForeignKey(User, on_delete=models.PROTECT, related_name='notas_despacho')
    observaciones = models.TextField(blank=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ['-fecha', '-id']
        verbose_name = 'nota de despacho'
        verbose_name_plural = 'notas de despacho'

    def save(self, *args, **kwargs):
        if not self.numero:
            from inventario.services import generar_numero_nd

            self.numero = generar_numero_nd()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.numero or f'Nota de despacho {self.pk}'


class DetalleDespacho(models.Model):
    despacho = models.ForeignKey(NotaDespacho, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name='detalles_despacho')
    cantidad = models.DecimalField(max_digits=10, decimal_places=3, validators=[MinValueValidator(Decimal('0.001'))])

    class Meta:
        verbose_name = 'detalle de despacho'
        verbose_name_plural = 'detalles de despacho'

    def __str__(self):
        return f'{self.producto} x {self.cantidad}'


class MovimientoLote(models.Model):
    class Tipo(models.TextChoices):
        DESPACHO = 'DESPACHO', 'Despacho'
        MERMA = 'MERMA', 'Merma'
        AJUSTE = 'AJUSTE', 'Ajuste'

    lote = models.ForeignKey(Lote, on_delete=models.PROTECT, related_name='movimientos')
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    cantidad = models.DecimalField(max_digits=10, decimal_places=3, validators=[MinValueValidator(Decimal('0.001'))])
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    referencia = GenericForeignKey('content_type', 'object_id')
    fecha = models.DateTimeField(auto_now_add=True)
    registrado_por = models.ForeignKey(User, on_delete=models.PROTECT, related_name='movimientos_lote')

    class Meta:
        ordering = ['-fecha', '-id']
        verbose_name = 'movimiento de lote'
        verbose_name_plural = 'movimientos de lote'

    def __str__(self):
        return f'{self.tipo} {self.cantidad} de {self.lote}'


class AjusteMerma(models.Model):
    class Motivo(models.TextChoices):
        VENCIMIENTO = 'VENCIMIENTO', 'Vencimiento'
        DANO = 'DANO', 'Daño'
        PROCESO = 'PROCESO', 'Proceso'
        OTRO = 'OTRO', 'Otro'

    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name='mermas')
    cantidad = models.DecimalField(max_digits=10, decimal_places=3, validators=[MinValueValidator(Decimal('0.001'))])
    motivo = models.CharField(max_length=20, choices=Motivo.choices)
    detalle = models.TextField(blank=True)
    fecha = models.DateField()
    registrado_por = models.ForeignKey(User, on_delete=models.PROTECT, related_name='ajustes_merma')
    history = HistoricalRecords()

    class Meta:
        ordering = ['-fecha', '-id']
        verbose_name = 'ajuste de merma'
        verbose_name_plural = 'ajustes de merma'

    def __str__(self):
        return f'{self.producto} - {self.cantidad} ({self.motivo})'


class SecuenciaDocumento(models.Model):
    tipo = models.CharField(max_length=2)
    anio = models.PositiveIntegerField()
    ultimo_numero = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tipo', 'anio'], name='secuencia_documento_tipo_anio_unica'),
        ]
        verbose_name = 'secuencia de documento'
        verbose_name_plural = 'secuencias de documentos'

    def __str__(self):
        return f'{self.tipo}-{self.anio}: {self.ultimo_numero}'
