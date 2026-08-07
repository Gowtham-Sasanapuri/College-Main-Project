import React from 'react'
import styles from "./navbar.module.css"
import videoIcon from "../../../assets/video-intelligence-api-svgrepo-com.svg";

const Navbar = () => {
    return (
        <>
            <div className={styles.bar}>
                <div className={styles.LogoContainer}>
                    <img src={videoIcon} alt="Meet Logo" className={styles.logo}/>
                    <p className={styles.AppName}>QuickMeet</p>
                </div>
            </div>
        </>
    )
}

export default Navbar
