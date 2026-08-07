import React from 'react'
import styles from "./Content.module.css"
const Content = () => {
    return (
        <div className={styles.Container}>
            <div className={styles.heading}>
                <h1 className={styles.headingContent}>Welcome to <span className={styles.inline}>QuickMeet</span></h1>
            </div>
            <div className={styles.SubContentContainer}>
                <p className={styles.SubContent}>Connect, collaborate and communicate seamlessly with secure video meetings.</p>
            </div>
        </div>
    )
}

export default Content
