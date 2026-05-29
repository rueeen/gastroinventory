from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from rest_framework import serializers

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
    UnidadMedida,
)
from inventario.services import generar_numero_nd, generar_numero_oc


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = ['id', 'nombre', 'descripcion']


class UnidadMedidaSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnidadMedida
        fields = ['id', 'nombre', 'abreviatura']


class ProductoSerializer(serializers.ModelSerializer):
    categoria_nombre = serializers.CharField(source='categoria.nombre', read_only=True)
    unidad_medida_abreviatura = serializers.CharField(source='unidad_medida.abreviatura', read_only=True)

    class Meta:
        model = Producto
        fields = [
            'id', 'nombre', 'categoria', 'categoria_nombre', 'unidad_medida', 'unidad_medida_abreviatura',
            'stock_actual', 'stock_minimo', 'peso_unitario_ref', 'activo', 'creado_en',
        ]
        read_only_fields = ['stock_actual', 'creado_en']


class DetalleOrdenCompraSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)

    class Meta:
        model = DetalleOrdenCompra
        fields = ['id', 'producto', 'producto_nombre', 'cantidad', 'precio_unitario']


class OrdenCompraSerializer(serializers.ModelSerializer):
    detalles = DetalleOrdenCompraSerializer(many=True)
    creado_por_nombre = serializers.CharField(source='creado_por.get_full_name', read_only=True)

    class Meta:
        model = OrdenCompra
        fields = ['id', 'numero', 'proveedor', 'fecha', 'estado', 'creado_por', 'creado_por_nombre', 'observaciones', 'creado_en', 'detalles']
        read_only_fields = ['numero', 'creado_por', 'creado_en']

    def validate_detalles(self, detalles):
        if not detalles and (not self.instance or self.instance.estado == OrdenCompra.Estado.BORRADOR):
            raise serializers.ValidationError('Debe ingresar al menos un detalle.')
        return detalles

    def validate(self, attrs):
        if self.instance:
            estado_actual = self.instance.estado
            nuevo_estado = attrs.get('estado', estado_actual)
            transiciones_validas = {
                OrdenCompra.Estado.BORRADOR: [
                    OrdenCompra.Estado.RECIBIDA,
                    OrdenCompra.Estado.ANULADA,
                ],
                OrdenCompra.Estado.RECIBIDA: [],
                OrdenCompra.Estado.ANULADA: [],
            }
            if nuevo_estado != estado_actual and nuevo_estado not in transiciones_validas.get(estado_actual, []):
                raise serializers.ValidationError({
                    'estado': f'No se puede cambiar el estado de {estado_actual} a {nuevo_estado}.'
                })
            if 'detalles' in attrs and estado_actual != OrdenCompra.Estado.BORRADOR:
                raise serializers.ValidationError({
                    'detalles': 'No se pueden modificar los detalles de una orden que ya no está en borrador.'
                })
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        detalles_data = validated_data.pop('detalles')
        request = self.context.get('request')
        validated_data['creado_por'] = request.user
        validated_data['numero'] = generar_numero_oc()
        orden = OrdenCompra.objects.create(**validated_data)
        for detalle_data in detalles_data:
            DetalleOrdenCompra.objects.create(orden=orden, **detalle_data)
        return orden

    @transaction.atomic
    def update(self, instance, validated_data):
        detalles_data = validated_data.pop('detalles', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if detalles_data is not None and instance.estado == OrdenCompra.Estado.BORRADOR:
            instance.detalles.all().delete()
            for detalle_data in detalles_data:
                DetalleOrdenCompra.objects.create(orden=instance, **detalle_data)
        return instance


class MovimientoLoteSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='lote.producto.nombre', read_only=True)
    lote_id = serializers.IntegerField(source='lote.id', read_only=True)

    class Meta:
        model = MovimientoLote
        fields = ['id', 'lote_id', 'producto_nombre', 'tipo', 'cantidad', 'fecha', 'registrado_por']
        read_only_fields = fields


class LoteSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    movimientos = MovimientoLoteSerializer(many=True, read_only=True)

    class Meta:
        model = Lote
        fields = [
            'id', 'producto', 'producto_nombre', 'orden_compra', 'cantidad_inicial', 'cantidad_disponible',
            'fecha_ingreso', 'fecha_vencimiento', 'activo', 'movimientos',
        ]
        read_only_fields = ['movimientos']


class DetalleDespachoSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)

    class Meta:
        model = DetalleDespacho
        fields = ['id', 'producto', 'producto_nombre', 'cantidad']


class NotaDespachoSerializer(serializers.ModelSerializer):
    detalles = DetalleDespachoSerializer(many=True)
    creado_por_nombre = serializers.CharField(source='creado_por.get_full_name', read_only=True)

    class Meta:
        model = NotaDespacho
        fields = ['id', 'numero', 'fecha', 'clase', 'docente', 'num_alumnos', 'estado', 'creado_por', 'creado_por_nombre', 'observaciones', 'detalles']
        read_only_fields = ['numero', 'creado_por']

    def validate_detalles(self, detalles):
        confirmando_despacho = (
            self.instance
            and self.partial
            and self.instance.estado == NotaDespacho.Estado.BORRADOR
            and self.initial_data.get('estado') == NotaDespacho.Estado.DESPACHADO
            and self.instance.detalles.exists()
        )
        if (
            not detalles
            and not confirmando_despacho
            and (not self.instance or self.instance.estado == NotaDespacho.Estado.BORRADOR)
        ):
            raise serializers.ValidationError('Debe ingresar al menos un detalle.')
        return detalles

    def _validar_stock_para_despacho(self, nota):
        errores = []
        for detalle in nota.detalles.select_related('producto__unidad_medida').all():
            disponible = (
                Lote.objects.filter(producto=detalle.producto, activo=True)
                .aggregate(t=Sum('cantidad_disponible'))['t']
                or Decimal('0.000')
            )
            if disponible < detalle.cantidad:
                errores.append(
                    f'{detalle.producto.nombre}: disponible {disponible} '
                    f'{detalle.producto.unidad_medida.abreviatura}, '
                    f'requerido {detalle.cantidad} '
                    f'{detalle.producto.unidad_medida.abreviatura}.'
                )
        if errores:
            raise serializers.ValidationError({
                'stock': errores
            })

    def validate(self, attrs):
        estado_actual = self.instance.estado if self.instance else NotaDespacho.Estado.BORRADOR
        nuevo_estado = attrs.get('estado', estado_actual)
        if self.instance:
            transiciones_validas = {
                NotaDespacho.Estado.BORRADOR: [
                    NotaDespacho.Estado.DESPACHADO,
                    NotaDespacho.Estado.ANULADO,
                ],
                NotaDespacho.Estado.DESPACHADO: [],
                NotaDespacho.Estado.ANULADO: [],
            }
            if nuevo_estado != estado_actual and nuevo_estado not in transiciones_validas.get(estado_actual, []):
                raise serializers.ValidationError({
                    'estado': f'No se puede cambiar el estado de {estado_actual} a {nuevo_estado}.'
                })
            if 'detalles' in attrs and estado_actual != NotaDespacho.Estado.BORRADOR:
                raise serializers.ValidationError({
                    'detalles': 'No se pueden modificar los detalles de una nota que ya no está en borrador.'
                })

        if (self.instance
                and nuevo_estado == NotaDespacho.Estado.DESPACHADO
                and estado_actual != NotaDespacho.Estado.DESPACHADO):
            self._validar_stock_para_despacho(self.instance)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        detalles_data = validated_data.pop('detalles')
        request = self.context.get('request')
        validated_data['creado_por'] = request.user
        validated_data['numero'] = generar_numero_nd()
        despacho = NotaDespacho.objects.create(**validated_data)
        for detalle_data in detalles_data:
            DetalleDespacho.objects.create(despacho=despacho, **detalle_data)
        return despacho

    @transaction.atomic
    def update(self, instance, validated_data):
        detalles_data = validated_data.pop('detalles', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if detalles_data is not None and instance.estado == NotaDespacho.Estado.BORRADOR:
            instance.detalles.all().delete()
            for detalle_data in detalles_data:
                DetalleDespacho.objects.create(despacho=instance, **detalle_data)
        return instance


class AjusteMermaSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    registrado_por_nombre = serializers.CharField(source='registrado_por.get_full_name', read_only=True)

    class Meta:
        model = AjusteMerma
        fields = ['id', 'producto', 'producto_nombre', 'cantidad', 'motivo', 'detalle', 'fecha', 'registrado_por', 'registrado_por_nombre']
        read_only_fields = ['registrado_por']

    def create(self, validated_data):
        request = self.context.get('request')
        validated_data['registrado_por'] = request.user
        return super().create(validated_data)
