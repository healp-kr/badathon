/* Leaflet 을 React 밖에 가둔다.
 *
 * 지도는 명령형 라이브러리라 React 의 렌더 주기와 맞지 않는다. 그래서 지도 인스턴스는
 * ref 에 두고, 이 훅이 생성·정리를 책임진다. 바닐라에서는 탭을 떠날 때 `BD.map.teardown()`
 * 을 직접 불러야 했고 빠뜨리면 지도가 유령처럼 남았는데, 여기서는 언마운트가 정리한다.
 *
 * react-leaflet 을 쓰지 않은 이유: 기존 map.js 가 이미 명령형으로 완성돼 있어서
 * 래퍼를 한 겹 더 두면 옮길 때 동작이 달라질 여지만 커진다.
 */
import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import type { 지도핀 } from '../../api/types';

const PIN = {
  예약: { color: '#0b7a37', fill: '#1db954' },
  일반: { color: '#3b4757', fill: '#8b95a5' },
  현위치: { color: '#1462c9', fill: '#4a90e2' },
} as const;

interface Options {
  center: [number, number];
  coords: { lat: number; lon: number } | null;
}

export function useLeafletMap({ center, coords }: Options) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markersRef = useRef<L.Layer[]>([]);
  const [tileFailed, setTileFailed] = useState(false);

  /* 지도 생성 — 마운트당 한 번. */
  useEffect(() => {
    const host = containerRef.current;
    if (!host) return;

    const map = L.map(host, { zoomControl: true, attributionControl: true }).setView(
      coords ? [coords.lat, coords.lon] : center,
      14,
    );
    mapRef.current = map;

    // 타일은 외부에서 온다. 실패해도 위치와 시설 핀은 그대로 보인다.
    const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    });
    tiles.on('tileerror', () => setTileFailed(true));
    tiles.addTo(map);

    if (coords) {
      L.circleMarker([coords.lat, coords.lon], {
        radius: 7,
        weight: 3,
        color: PIN.현위치.color,
        fillColor: PIN.현위치.fill,
        fillOpacity: 1,
      })
        .addTo(map)
        .bindTooltip('현재 위치');
    }

    // 컨테이너 크기가 잡힌 뒤에야 타일이 맞게 깔린다
    const timer = window.setTimeout(() => map.invalidateSize(), 60);

    return () => {
      window.clearTimeout(timer);
      map.remove();
      mapRef.current = null;
      markersRef.current = [];
    };
    // center/coords 변경 시 지도를 다시 만들지 않는다 — setView 로 옮기는 편이 낫다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function drawBoundary(geo: GeoJSON.FeatureCollection) {
    const map = mapRef.current;
    if (!map) return;
    L.geoJSON(geo, {
      style: { color: '#0b7a37', weight: 2, fillColor: '#1db954', fillOpacity: 0.06 },
    }).addTo(map);
  }

  function clearPins() {
    const map = mapRef.current;
    markersRef.current.forEach((m) => map?.removeLayer(m));
    markersRef.current = [];
  }

  function drawPins(pins: 지도핀[], onPick: (index: number) => void) {
    const map = mapRef.current;
    if (!map) return;
    clearPins();

    pins.forEach((pin, index) => {
      const style = pin.예약 ? PIN.예약 : PIN.일반;
      const marker = L.circleMarker([pin.위도, pin.경도], {
        radius: 9,
        weight: 2,
        color: style.color,
        fillColor: style.fill,
        fillOpacity: 0.9,
      }).addTo(map);
      marker.bindTooltip(pin.시설명);
      marker.on('click', () => onPick(index));
      markersRef.current.push(marker);
    });

    if (pins.length) {
      const bounds = L.latLngBounds(pins.map((p) => [p.위도, p.경도] as [number, number]));
      if (coords) bounds.extend([coords.lat, coords.lon]);
      map.fitBounds(bounds.pad(0.15), { maxZoom: 16 });
    }
  }

  return { containerRef, drawBoundary, drawPins, clearPins, tileFailed };
}
