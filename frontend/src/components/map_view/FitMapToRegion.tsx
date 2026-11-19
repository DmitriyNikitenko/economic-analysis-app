import { useEffect } from "react";  // useEffect - выполняет действия при изменении зависимостей
import { useMap } from "react-leaflet";  // useMap - Даёт доступ к экземпляру карты Leaflet
import type { LatLngBounds } from "leaflet";  // LatLngBounds - типы границ Leaflet

// Настройка границ карты (ограничение области просмотра) на основе геометрии районов (целой области)
export function FitMapToRegion({ bounds }: { bounds: LatLngBounds }) {
    const map = useMap();

    useEffect(() => {
        if (bounds.isValid()) {
            map.fitBounds(bounds, { padding: [12, 12], maxZoom: 9, animate: false });
            map.setMaxBounds(bounds);
        }
    }, [bounds, map]);

    return null;
}