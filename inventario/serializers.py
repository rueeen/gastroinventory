from django.db import transaction
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
from inventario.services import generar_numero_nd, generar_numero_oc, procesar_despacho_fifo


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
        if not detalles:
            raise serializers.ValidationError('Debe ingresar al menos un detalle.')
        return detalles

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
        if not detalles:
            raise serializers.ValidationError('Debe ingresar al menos un detalle.')
        return detalles

    @transaction.atomic
    def create(self, validated_data):
        detalles_data = validated_data.pop('detalles')
        request = self.context.get('request')
        validated_data['creado_por'] = request.user
        validated_data['numero'] = generar_numero_nd()
        despacho = NotaDespacho.objects.create(**validated_data)
        for detalle_data in detalles_data:
            DetalleDespacho.objects.create(despacho=despacho, **detalle_data)
        if despacho.estado == NotaDespacho.Estado.DESPACHADO:
            procesar_despacho_fifo(despacho)
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
