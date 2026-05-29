from rest_framework.permissions import BasePermission


class EsAdministrador(BasePermission):
    message = 'Se requiere pertenecer al grupo Administrador.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.groups.filter(name='Administrador').exists())


class EsBodeguero(BasePermission):
    message = 'Se requiere pertenecer al grupo Bodeguero.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.groups.filter(name='Bodeguero').exists())


class EsAdminOBodeguero(BasePermission):
    message = 'Se requiere pertenecer a Administrador o Bodeguero.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.groups.filter(name__in=['Administrador', 'Bodeguero']).exists()
