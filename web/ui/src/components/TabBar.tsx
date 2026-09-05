/* 하단 탭 — 추천·지도·기록을 오가는 앱의 뼈대.
 *
 * 활성은 아이콘 채움 + 초록 라벨, 비활성은 아웃라인 회색으로 말한다.
 * 배지 슬롯(빨간 점)은 자리를 마련해 두었을 뿐 지금은 아무도 켜지 않는다 —
 * 알림이 생기면 `badges` 에 탭 이름을 넣으면 된다.
 */
import { useApp, type Tab } from '../state/AppContext';
import Icon, { type IconName } from './icons';
import styles from './TabBar.module.css';

const TABS: Tab[] = ['홈', '운동', '지도', '기록'];

export default function TabBar({ badges = [] }: { badges?: Tab[] }) {
  const { tab, setTab } = useApp();

  return (
    <nav className={styles.tabs}>
      {TABS.map((name) => {
        const active = tab === name;
        return (
          <button
            key={name}
            type="button"
            aria-current={active}
            onClick={() => setTab(name)}
          >
            <span className={styles.slot}>
              <Icon name={name as IconName} filled={active} />
              {badges.includes(name) && <span className={styles.dot} aria-hidden="true" />}
            </span>
            {name}
          </button>
        );
      })}
    </nav>
  );
}
