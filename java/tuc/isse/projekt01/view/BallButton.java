package tuc.isse.projekt01.view;

import javax.swing.JButton;
import java.awt.Color;
import java.awt.Graphics;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.BasicStroke;
import tuc.isse.projekt01.model.*;

/**
 * Projekt 04, Task d: BallButton - Helper Class for DegreeFrame
 * 
 * Custom JButton implementation to visually represent game board cells.
 * Each button can display a ball (white or black circle) and shows:
 * - Regular balls as white or black filled circles
 * - King balls with yellow (WHITE king) or purple (BLACK king) fill
 * - Blue border when selected by the user
 * 
 * This class handles the custom painting of balls and provides visual feedback
 * for user interaction in the GUI.
 * 
 * @author xiajiong.xu@tu-clausthal.de
 * @version 1.0
 */
public class BallButton extends JButton {

    private Ball ball;
    private boolean selected = false;

    public BallButton() {
        setFocusPainted(false);
        setContentAreaFilled(false);
        setOpaque(true);
        setBackground(new Color(220, 230, 240)); // light board color
    }

    /**
     * Set the ball to display on this button
     * @param ball The ball to display (or null for empty)
     */
    public void setBall(Ball ball) {
        this.ball = ball;
        repaint();
    }

    /**
     * Set whether this button is currently selected
     * @param selected True to show selection border, false otherwise
     */
    public void setSelected(boolean selected) {
        this.selected = selected;
        repaint();
    }

    /**
     * Custom painting for the ball button
     * @param g Graphics context for drawing
     */
    @Override
    protected void paintComponent(Graphics g) {
        super.paintComponent(g);

        if (ball == null) return;

        Graphics2D g2 = (Graphics2D) g;
        g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING,
                RenderingHints.VALUE_ANTIALIAS_ON);

        int size = Math.min(getWidth(), getHeight()) - 16;

        int x = (getWidth() - size) / 2;
        int y = (getHeight() - size) / 2;

        // Color Logic for balls
        if (ball.getRole() == Role.KING) {
            if (ball.getColor() == tuc.isse.projekt01.model.Color.WHITE) {
                g2.setColor(Color.YELLOW);   // White King = Yellow
            } else {
                g2.setColor(new Color(128, 0, 128)); // Black King = Purple
            }
        } else {
            if (ball.getColor() == tuc.isse.projekt01.model.Color.WHITE) {
                g2.setColor(Color.WHITE); // White Resident = White
            } else {
                g2.setColor(Color.BLACK); // Black Resident = Black
            }
        }

        g2.fillOval(x, y, size, size);

        // outline
        g2.setColor(Color.DARK_GRAY);
        g2.drawOval(x, y, size, size);

        // Selection Border
        if (selected) {
            g2.setColor(Color.BLUE); // Once selected = Blue border
            g2.setStroke(new BasicStroke(3));
            g2.drawRect(2, 2, getWidth() - 4, getHeight() - 4);
        }
    }
}
