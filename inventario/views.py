from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import TruncWeek
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from inventario.models import AjusteMerma, Categoria, Lote, MovimientoLote, NotaDespacho, OrdenCompra, Producto, UnidadMedida
from inventario.permissions import EsAdministrador, EsAdminOBodeguero
from inventario.serializers import (
    AjusteMermaSerializer,
    CategoriaSerializer,
    LoteSerializer,
    NotaDespachoSerializer,
    OrdenCompraSerializer,
    ProductoSerializer,
    UnidadMedidaSerializer,
)
from inventario.services import generar_pdf


class CategoriaViewSet(viewsets.ModelViewSet):
    queryset = Categoria.objects.all()
    serializer_class = CategoriaSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [EsAdministrador()]
        return [EsAdminOBodeguero()]


class UnidadMedidaViewSet(viewsets.ModelViewSet):
    queryset = UnidadMedida.objects.all()
    serializer_class = UnidadMedidaSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [EsAdministrador()]
        return [EsAdminOBodeguero()]


class ProductoViewSet(viewsets.ModelViewSet):
    serializer_class = ProductoSerializer

    def get_queryset(self):
        queryset = Producto.objects.select_related('categoria', 'unidad_medida').all()
        categoria = self.request.query_params.get('categoria')
        activo = self.request.query_params.get('activo')
        if categoria:
            queryset = queryset.filter(categoria_id=categoria)
        if activo is not None:
            queryset = queryset.filter(activo=activo.lower() == 'true')
        return queryset

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [EsAdministrador()]
        return [EsAdminOBodeguero()]

    def destroy(self, request, *args, **kwargs):
        producto = self.get_object()
        producto.activo = False
        producto.save(update_fields=['activo'])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'])
    def bajo_stock(self, request):
        productos = self.get_queryset().filter(activo=True, stock_actual__lte=F('stock_minimo'))
        serializer = self.get_serializer(productos, many=True)
        return Response(serializer.data)


class OrdenCompraViewSet(viewsets.ModelViewSet):
    serializer_class = OrdenCompraSerializer

    def get_queryset(self):
        queryset = OrdenCompra.objects.select_related('creado_por').prefetch_related('detalles__producto').all()
        estado = self.request.query_params.get('estado')
        fecha = self.request.query_params.get('fecha')
        fecha_desde = self.request.query_params.get('fecha_desde')
        fecha_hasta = self.request.query_params.get('fecha_hasta')
        if estado:
            queryset = queryset.filter(estado=estado)
        if fecha:
            queryset = queryset.filter(fecha=fecha)
        if fecha_desde:
            queryset = queryset.filter(fecha__gte=fecha_desde)
        if fecha_hasta:
            queryset = queryset.filter(fecha__lte=fecha_hasta)
        return queryset

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'pdf']:
            return [EsAdministrador()]
        return [EsAdminOBodeguero()]

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, *args, **kwargs):
        try:
            return super().update(request, *args, **kwargs)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def pdf(self, request, pk=None):
        orden = self.get_object()
        pdf_file = generar_pdf('inventario/orden_compra_pdf.html', {'orden': orden})
        response = HttpResponse(pdf_file, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{orden.numero}.pdf"'
        return response


class LoteViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = LoteSerializer
    permission_classes = [EsAdminOBodeguero]

    def get_queryset(self):
        queryset = Lote.objects.select_related('producto', 'orden_compra').prefetch_related('movimientos').all()
        producto = self.request.query_params.get('producto')
        activo = self.request.query_params.get('activo')
        vencimiento = self.request.query_params.get('vencimiento')
        if producto:
            queryset = queryset.filter(producto_id=producto)
        if activo is not None:
            queryset = queryset.filter(activo=activo.lower() == 'true')
        if vencimiento:
            queryset = queryset.filter(fecha_vencimiento__lte=vencimiento)
        return queryset


class NotaDespachoViewSet(viewsets.ModelViewSet):
    serializer_class = NotaDespachoSerializer
    permission_classes = [EsAdminOBodeguero]

    def get_queryset(self):
        queryset = NotaDespacho.objects.select_related('creado_por').prefetch_related('detalles__producto').all()
        fecha = self.request.query_params.get('fecha')
        fecha_desde = self.request.query_params.get('fecha_desde')
        fecha_hasta = self.request.query_params.get('fecha_hasta')
        clase = self.request.query_params.get('clase')
        if fecha:
            queryset = queryset.filter(fecha=fecha)
        if fecha_desde:
            queryset = queryset.filter(fecha__gte=fecha_desde)
        if fecha_hasta:
            queryset = queryset.filter(fecha__lte=fecha_hasta)
        if clase:
            queryset = queryset.filter(clase__icontains=clase)
        return queryset

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, *args, **kwargs):
        try:
            return super().update(request, *args, **kwargs)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def pdf(self, request, pk=None):
        despacho = self.get_object()
        pdf_file = generar_pdf('inventario/despacho_pdf.html', {'despacho': despacho})
        response = HttpResponse(pdf_file, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{despacho.numero}.pdf"'
        return response


class AjusteMermaViewSet(viewsets.ModelViewSet):
    serializer_class = AjusteMermaSerializer
    permission_classes = [EsAdminOBodeguero]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        queryset = AjusteMerma.objects.select_related('producto', 'registrado_por').all()
        producto = self.request.query_params.get('producto')
        fecha = self.request.query_params.get('fecha')
        fecha_desde = self.request.query_params.get('fecha_desde')
        fecha_hasta = self.request.query_params.get('fecha_hasta')
        if producto:
            queryset = queryset.filter(producto_id=producto)
        if fecha:
            queryset = queryset.filter(fecha=fecha)
        if fecha_desde:
            queryset = queryset.filter(fecha__gte=fecha_desde)
        if fecha_hasta:
            queryset = queryset.filter(fecha__lte=fecha_hasta)
        return queryset

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([EsAdministrador])
def dashboard_resumen(request):
    hoy = timezone.localdate()
    data = {
        'productos_activos': Producto.objects.filter(activo=True).count(),
        'stock_total': Producto.objects.filter(activo=True).aggregate(total=Sum('stock_actual'))['total'] or 0,
        'alertas_bajo_stock': Producto.objects.filter(activo=True, stock_actual__lte=F('stock_minimo')).count(),
        'movimientos_hoy': MovimientoLote.objects.filter(fecha__date=hoy).count(),
    }
    return Response(data)


@api_view(['GET'])
@permission_classes([EsAdministrador])
def reporte_consumo_semanal(request):
    data = (
        MovimientoLote.objects.filter(tipo=MovimientoLote.Tipo.DESPACHO)
        .annotate(semana=TruncWeek('fecha'))
        .values('semana', 'lote__producto__categoria__nombre')
        .annotate(total=Sum('cantidad'), movimientos=Count('id'))
        .order_by('-semana', 'lote__producto__categoria__nombre')
    )
    return Response(list(data))


@api_view(['GET'])
@permission_classes([EsAdministrador])
def reporte_top_mermas(request):
    data = (
        MovimientoLote.objects.filter(tipo=MovimientoLote.Tipo.MERMA)
        .values('lote__producto_id', 'lote__producto__nombre')
        .annotate(total_merma=Sum('cantidad'))
        .order_by('-total_merma')[:10]
    )
    return Response(list(data))
