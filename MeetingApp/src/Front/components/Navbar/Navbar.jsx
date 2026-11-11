import React from 'react';
import styles from './navbar.module.css';
import videoIcon from '../../../assets/video-intelligence-api-svgrepo-com.svg';
import { useTheme } from '../../../utils/ThemeContext';

const Navbar = () => {
    const { isDark, toggleTheme } = useTheme();

    return (
        <header className={styles.bar}>
            <div className={styles.LogoContainer}>
                <div className={styles.logoBadge}>
                    <img src={videoIcon} alt="MeetSpace Logo" className={styles.logo} />
                </div>
                <div className={styles.brandGroup}>
                    <span className={styles.AppName}>MeetSpace</span>
                    <span className={styles.appTag}>Conferencing</span>
                </div>
            </div>
            <div className={styles.navRight}>
                <div className={styles.systemStatus}>
                    <span className={styles.statusDot} />
                    <span className={styles.statusText}>Network Live</span>
                </div>
                <button
                    type="button"
                    className={styles.themeToggle}
                    onClick={toggleTheme}
                    title={`Switch to ${isDark ? 'Light' : 'Dark'} mode`}
                    aria-label={`Switch to ${isDark ? 'Light' : 'Dark'} mode`}
                >
                    <span>{isDark ? '☀️ Light' : '🌙 Dark'}</span>
                </button>
            </div>
        </header>
    );
};

export default Navbar;
